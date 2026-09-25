# -*- coding: utf-8 -*-
"""Importación de los detalles del Registro de Compras y Ventas (RCV) descargados del SII.

Ruta real: wizard/rcv_import.py
"""
import base64

from odoo import fields, models
from odoo.exceptions import UserError

from ..models.f29_rules import parse_rcv


class TfL10nClF29RcvImport(models.TransientModel):
    _name = 'tf_l10n_cl.f29.rcv.import'
    _description = 'Importar RCV para el F29'

    f29_id = fields.Many2one('tf_l10n_cl.f29', required=True, readonly=True)
    sales_file = fields.Binary(string='Detalle de ventas (CSV)')
    sales_filename = fields.Char()
    purchases_file = fields.Binary(string='Detalle de compras (CSV)')
    purchases_filename = fields.Char()

    def action_import(self):
        self.ensure_one()
        rows, kinds = [], set()
        for content, expected, label in ((self.sales_file, 'sale', self.env._('ventas')),
                                         (self.purchases_file, 'purchase', self.env._('compras'))):
            if not content:
                continue
            try:
                kind, file_rows = parse_rcv(base64.b64decode(content))
            except ValueError as error:
                raise UserError(self.env._('Archivo de %(label)s: %(error)s', label=label, error=error)) from error
            if kind != expected:
                raise UserError(self.env._('El archivo cargado como %s corresponde al otro registro del RCV.', label))
            rows += file_rows
            kinds.add(kind)
        if not kinds:
            raise UserError(self.env._('Cargue al menos un archivo del RCV.'))
        if not self.f29_id.line_ids:
            self.f29_id._tf_compute()
        self.f29_id._tf_apply_rcv(rows, kinds)
        return {'type': 'ir.actions.act_window_close'}
