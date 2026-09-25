# -*- coding: utf-8 -*-
"""Tipo de documento SII y folio de las facturas de proveedor, para el F29 y el RCV.

Ruta real: models/account_move.py
"""
from odoo import api, fields, models

from .f29_rules import PURCHASE_DOCUMENT_TYPES


class AccountMove(models.Model):
    _inherit = 'account.move'

    tf_dte_cl_purchase_document_type = fields.Selection(
        PURCHASE_DOCUMENT_TYPES, string='Tipo de documento SII (compra)',
        compute='_compute_tf_dte_cl_purchase_document_type', store=True, readonly=False, index=True,
        help='Cómo se declara esta compra en el F29. Se completa solo en las facturas creadas desde '
             'Documentos recibidos.',
    )
    tf_dte_cl_purchase_folio = fields.Integer(string='Folio del proveedor', copy=False, index=True)

    @api.depends('move_type')
    def _compute_tf_dte_cl_purchase_document_type(self):
        for move in self:
            if move.tf_dte_cl_purchase_document_type or move.move_type not in ('in_invoice', 'in_refund'):
                continue
            move.tf_dte_cl_purchase_document_type = '61' if move.move_type == 'in_refund' else '33'
