# -*- coding: utf-8 -*-
"""Declaración F29: cálculo de los códigos desde Odoo y comparación con el RCV del SII.

Ruta real: models/f29.py
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.tf_dte_cl.models.res_partner import normalize_rut

from . import f29_rules as rules

STATES = [('draft', 'Borrador'), ('presented', 'Presentada')]
MONTHS = [(str(m), name) for m, name in enumerate(
    ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto',
     'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'], start=1)]
SECTIONS = [('ventas', 'Ventas exentas'), ('debitos', 'Débitos'), ('compras', 'Compras sin crédito'),
            ('creditos', 'Créditos'), ('resultado', 'Resultado IVA'), ('renta', 'Retenciones y PPM'),
            ('total', 'Total')]
SECTION_OF = {code: section for code, _name, section in rules.CODES}
PURCHASE_TYPES_IN_F29 = {code for code, _l in rules.PURCHASE_DOCUMENT_TYPES} - {'bhe', 'other'}


class TfL10nClF29(models.Model):
    _name = 'tf_l10n_cl.f29'
    _description = 'Declaración F29'
    _inherit = ['mail.thread']
    _order = 'year desc, month desc'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    year = fields.Integer(string='Año', required=True, default=lambda self: fields.Date.context_today(self).year)
    month = fields.Selection(MONTHS, string='Mes', required=True,
                             default=lambda self: str(fields.Date.context_today(self).month))
    date_from = fields.Date(compute='_compute_dates')
    date_to = fields.Date(compute='_compute_dates')
    state = fields.Selection(STATES, string='Estado', default='draft', required=True, tracking=True)

    ppm_rate = fields.Float(string='Tasa PPM (%)', digits=(4, 1),
                            default=lambda self: self._tf_default_ppm_rate(),
                            help='Código 115. Se propone la del F29 anterior.')
    ppv_credit = fields.Integer(string='Crédito PPV (código 68)')
    previous_remainder = fields.Integer(
        string='Remanente del mes anterior (código 77)',
        help='Se toma del F29 del mes anterior si existe en Odoo; si no, ingréselo.')
    utm_previous = fields.Float(string='UTM del mes anterior')
    utm_current = fields.Float(string='UTM del período')
    remainder_readjusted = fields.Boolean(string='Remanente reajustado', readonly=True)

    line_ids = fields.One2many('tf_l10n_cl.f29.line', 'f29_id', string='Códigos', readonly=True)
    comparison_ids = fields.One2many('tf_l10n_cl.f29.comparison', 'f29_id', string='Comparación con el RCV',
                                     readonly=True)
    rcv_imported = fields.Boolean(string='RCV importado', readonly=True)
    warnings = fields.Text(string='Avisos', readonly=True)
    total_to_pay = fields.Integer(string='Total a pagar (código 91)', readonly=True)
    computed_at = fields.Datetime(string='Calculado', readonly=True)

    _sql_constraints = [
        ('period_uniq', 'unique(company_id, year, month)', 'Ya existe un F29 para ese período.'),
    ]

    @api.depends('year', 'month')
    def _compute_name(self):
        for f29 in self:
            f29.name = 'F29 %02d-%s' % (int(f29.month or 0), f29.year or '')

    @api.depends('year', 'month')
    def _compute_dates(self):
        for f29 in self:
            if f29.year and f29.month:
                month = int(f29.month)
                f29.date_from = date(f29.year, month, 1)
                f29.date_to = date(f29.year, month, calendar.monthrange(f29.year, month)[1])
            else:
                f29.date_from = f29.date_to = False

    @api.model
    def _tf_default_ppm_rate(self):
        previous = self.search([('company_id', '=', self.env.company.id)], limit=1)
        return previous.ppm_rate

    def _tf_previous(self):
        self.ensure_one()
        year, month = (self.year, int(self.month) - 1) if int(self.month) > 1 else (self.year - 1, 12)
        return self.search([('company_id', '=', self.company_id.id), ('year', '=', year), ('month', '=', str(month))],
                           limit=1)

    # ------------------------------------------------------------------
    # Datos del período
    # ------------------------------------------------------------------
    def _tf_tax_amounts(self, move) -> tuple[dict, set]:
        """Montos por categoría F29 de las líneas de impuesto de un asiento, y categorías sin cálculo."""
        amounts, other = defaultdict(float), set()
        for line in move.line_ids.filtered('tax_line_id'):
            category = line.tax_line_id._tf_dte_cl_f29_resolved_category()
            if category == 'iva_no_credit':
                amounts['no_credit_base'] += abs(line.tax_base_amount)
            elif category in ('iva_debit', 'iva_credit', 'iva_fixed_asset', 'iva_supermarket', 'withholding_fees'):
                amounts[category] += abs(line.balance)
            else:
                other.add(category or 'sin_categoria')
        return amounts, other

    def _tf_sales(self):
        moves = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'posted'),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('tf_dte_cl_document_type', 'in', rules.SALE_DOCUMENT_TYPES),
            ('invoice_date', '>=', self.date_from), ('invoice_date', '<=', self.date_to),
        ])
        docs, warnings = [], []
        for move in moves:
            expected = move._tf_dte_cl_expected_amounts()
            docs.append(rules.SaleDoc(
                move.tf_dte_cl_document_type, net=rules.round_peso(expected['MntNeto']),
                exempt=rules.round_peso(expected['MntExe']), iva=rules.round_peso(expected['MntIVA']), ref=move.id,
            ))
            if move.tf_dte_cl_document_type == '33' and expected['MntExe']:
                warnings.append('%s tiene montos exentos: revisar los códigos 586 y 142.' % move.name)
            if expected['ImptoReten']:
                warnings.append('%s tiene impuestos adicionales, que el cálculo no incluye.' % move.name)
        return moves, docs, warnings

    def _tf_purchases(self):
        moves = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'posted'),
            ('move_type', 'in', ('in_invoice', 'in_refund')),
            ('tf_dte_cl_purchase_document_type', 'in', list(PURCHASE_TYPES_IN_F29)),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
        ])
        docs, warnings = [], []
        for move in moves:
            amounts, other = self._tf_tax_amounts(move)
            exempt = sum(abs(line.balance) for line in move.invoice_line_ids
                         if line.display_type == 'product' and not line.tax_ids)
            docs.append(rules.PurchaseDoc(
                move.tf_dte_cl_purchase_document_type, net=rules.round_peso(abs(move.amount_untaxed_signed)),
                exempt=rules.round_peso(exempt), iva_credit=rules.round_peso(amounts['iva_credit']),
                iva_fixed_asset=rules.round_peso(amounts['iva_fixed_asset']),
                iva_supermarket=rules.round_peso(amounts['iva_supermarket']),
                no_credit_base=rules.round_peso(amounts['no_credit_base']), ref=move.id,
            ))
            if other - {'withholding_fees'}:
                warnings.append('%s tiene impuestos que el cálculo no incluye (%s).' % (
                    move.name, ', '.join(sorted(other))))
        return moves, docs, warnings

    def _tf_fees(self) -> tuple[int, list]:
        """Código 151: retenciones de honorarios según la fecha de pago (se declaran el mes siguiente al pago)."""
        total, refs = 0.0, []
        bills = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'posted'), ('move_type', '=', 'in_invoice'),
            ('line_ids.tax_line_id.tf_dte_cl_f29_category', '=', 'withholding_fees'),
        ])
        for bill in bills:
            retention = sum(abs(l.balance) for l in bill.line_ids.filtered('tax_line_id')
                            if l.tax_line_id._tf_dte_cl_f29_resolved_category() == 'withholding_fees')
            payable = bill.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable')
            due = abs(sum(payable.mapped('balance')))
            paid = sum(p.amount for p in payable.matched_debit_ids
                       if p.max_date and self.date_from <= p.max_date <= self.date_to)
            if retention and due and paid:
                total += retention * min(paid / due, 1.0)
                refs.append(bill.id)
        return rules.round_peso(total), refs

    # ------------------------------------------------------------------
    # Cálculo
    # ------------------------------------------------------------------
    def action_compute(self):
        for f29 in self:
            f29._tf_compute()
        return True

    def _tf_compute(self):
        self.ensure_one()
        if self.state == 'presented':
            raise UserError(self.env._('La declaración ya fue presentada. Vuelva a borrador para recalcular.'))
        pending = self.env['account.tax'].with_context(active_test=False).search([
            ('company_id', '=', self.company_id.id), ('tf_dte_cl_f29_category', '=', False),
        ])
        for tax in pending:
            tax._tf_dte_cl_f29_resolved_category()
        previous = self._tf_previous()
        if previous:
            previous_77 = int(previous.line_ids.filtered(lambda l: l.code == '77').value or 0)
            self.previous_remainder = previous_77
        remainder, readjusted = rules.readjusted_remainder(self.previous_remainder, self.utm_previous, self.utm_current)
        _sales_moves, sales, warnings = self._tf_sales()
        _purchase_moves, purchases, purchase_warnings = self._tf_purchases()
        fees, fee_refs = self._tf_fees()
        documents = {}
        codes = rules.compute_codes(sales, purchases, fees, remainder, self.ppm_rate, self.ppv_credit, documents)
        documents['151'] = fee_refs
        warnings += purchase_warnings
        if self.previous_remainder and not readjusted:
            warnings.append('El remanente (código 504) no está reajustado: ingrese la UTM de ambos meses.')
        rcv = {line.code: line.rcv_value for line in self.line_ids if line.rcv_available}
        self.line_ids.unlink()
        self.write({
            'line_ids': [fields.Command.create({
                'sequence': sequence,
                'code': code,
                'name': name,
                'section': section,
                'value': codes[code],
                'move_ids': [fields.Command.set(documents.get(code, []))],
                'rcv_available': code in rcv,
                'rcv_value': rcv.get(code, 0),
            }) for sequence, (code, name, section) in enumerate(rules.CODES)],
            'warnings': '\n'.join(warnings) or False,
            'remainder_readjusted': readjusted,
            'total_to_pay': codes['91'],
            'computed_at': fields.Datetime.now(),
        })

    def action_present(self):
        for f29 in self:
            if not f29.line_ids:
                raise UserError(self.env._('Calcule la declaración antes de marcarla como presentada.'))
            f29.state = 'presented'
        return True

    def action_draft(self):
        self.write({'state': 'draft'})
        return True

    # ------------------------------------------------------------------
    # Comparación con el RCV
    # ------------------------------------------------------------------
    def _tf_odoo_documents(self) -> dict:
        """Documentos de Odoo en el formato de comparación: (tipo, TipoDTE, RUT, folio) → {total, iva}."""
        result = {}
        sale_moves, _docs, _w = self._tf_sales()
        for move in sale_moves:
            expected = move._tf_dte_cl_expected_amounts()
            key = ('sale', move.tf_dte_cl_document_type,
                   normalize_rut(move.partner_id.commercial_partner_id.vat) or '', move.tf_dte_cl_folio)
            result[key] = {'total': rules.round_peso(move.amount_total), 'iva': rules.round_peso(expected['MntIVA']),
                           'move_id': move.id}
        purchase_moves, _docs, _w = self._tf_purchases()
        for move in purchase_moves:
            amounts, _other = self._tf_tax_amounts(move)
            key = ('purchase', move.tf_dte_cl_purchase_document_type,
                   normalize_rut(move.partner_id.commercial_partner_id.vat) or '', move.tf_dte_cl_purchase_folio)
            iva = amounts['iva_credit'] + amounts['iva_fixed_asset'] + amounts['iva_supermarket']
            result[key] = {'total': rules.round_peso(abs(move.amount_total_signed)), 'iva': rules.round_peso(iva),
                           'move_id': move.id}
        return result

    def _tf_apply_rcv(self, rows: list, kinds: set | None = None):
        """Guarda la comparación documento a documento y los códigos del RCV en cada línea.

        ``kinds``: registros cargados ('sale', 'purchase'), aunque vengan sin documentos.
        """
        self.ensure_one()
        rcv_docs = {}
        for row in rows:
            key = (row.kind, row.doc_type, normalize_rut(row.rut) or row.rut, row.folio)
            iva = row.iva + row.iva_fixed_asset if row.kind == 'purchase' else row.iva
            rcv_docs[key] = {'total': row.total, 'iva': iva, 'name': row.name}
        odoo_docs = self._tf_odoo_documents()
        kinds = set(kinds or {row.kind for row in rows})
        odoo_docs = {k: v for k, v in odoo_docs.items() if k[0] in kinds}
        comparison = rules.compare_documents(odoo_docs, rcv_docs)
        codes = rules.rcv_codes(rows)
        self.comparison_ids.filtered(lambda c: c.kind in kinds).unlink()
        self.write({
            'rcv_imported': True,
            'comparison_ids': [fields.Command.create({
                'kind': item['kind'], 'doc_type': item['doc_type'], 'rut': item['rut'], 'folio': item['folio'],
                'status': item['status'],
                'name': rcv_docs.get((item['kind'], item['doc_type'], item['rut'], item['folio']), {}).get('name'),
                'move_id': odoo_docs.get((item['kind'], item['doc_type'], item['rut'], item['folio']), {}).get('move_id'),
                'odoo_total': item['odoo_total'], 'sii_total': item['sii_total'],
                'odoo_iva': item['odoo_iva'], 'sii_iva': item['sii_iva'],
            }) for item in comparison],
        })
        for line in self.line_ids:
            if line.code in codes and SECTION_OF[line.code] in self._tf_sections_for(kinds):
                line.write({'rcv_available': True, 'rcv_value': codes[line.code]})

    @staticmethod
    def _tf_sections_for(kinds: set) -> set:
        sections = set()
        if 'sale' in kinds:
            sections |= {'ventas', 'debitos'}
        if 'purchase' in kinds:
            sections |= {'compras', 'creditos'}
        return sections

    def action_import_rcv(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.env._('Importar RCV'),
            'res_model': 'tf_l10n_cl.f29.rcv.import', 'view_mode': 'form', 'target': 'new',
            'context': {'default_f29_id': self.id},
        }


class TfL10nClF29Line(models.Model):
    _name = 'tf_l10n_cl.f29.line'
    _description = 'Código del F29'
    _order = 'f29_id, sequence'

    f29_id = fields.Many2one('tf_l10n_cl.f29', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer()
    code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Descripción')
    section = fields.Selection(SECTIONS, string='Sección')
    value = fields.Float(string='Odoo', digits=(16, 1))
    rcv_available = fields.Boolean()
    rcv_value = fields.Float(string='RCV del SII', digits=(16, 1))
    difference = fields.Float(string='Diferencia', compute='_compute_difference', digits=(16, 1))
    move_ids = fields.Many2many('account.move', string='Documentos')

    @api.depends('value', 'rcv_value', 'rcv_available')
    def _compute_difference(self):
        for line in self:
            line.difference = line.value - line.rcv_value if line.rcv_available else 0

    def action_open_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': '%s - %s' % (self.code, self.name),
            'res_model': 'account.move', 'view_mode': 'list,form', 'domain': [('id', 'in', self.move_ids.ids)],
        }


class TfL10nClF29Comparison(models.Model):
    _name = 'tf_l10n_cl.f29.comparison'
    _description = 'Comparación de documentos con el RCV'
    _order = 'f29_id, status, kind, doc_type, folio'

    f29_id = fields.Many2one('tf_l10n_cl.f29', required=True, ondelete='cascade', index=True)
    kind = fields.Selection([('sale', 'Venta'), ('purchase', 'Compra')], string='Registro')
    doc_type = fields.Char(string='Tipo')
    rut = fields.Char(string='RUT')
    name = fields.Char(string='Razón social (SII)')
    folio = fields.Integer(string='Folio')
    move_id = fields.Many2one('account.move', string='Documento en Odoo')
    status = fields.Selection([
        ('missing_odoo', 'Solo en el SII'),
        ('missing_sii', 'Solo en Odoo'),
        ('difference', 'Montos distintos'),
        ('match', 'Coincide'),
    ], string='Resultado')
    odoo_total = fields.Integer(string='Total Odoo')
    sii_total = fields.Integer(string='Total SII')
    odoo_iva = fields.Integer(string='IVA Odoo')
    sii_iva = fields.Integer(string='IVA SII')
