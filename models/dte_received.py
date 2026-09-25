# -*- coding: utf-8 -*-
"""Las facturas creadas desde Documentos recibidos llevan su tipo y folio SII.

Ruta real: models/dte_received.py
"""
from odoo import models

from .f29_rules import PURCHASE_DOCUMENT_TYPES

KNOWN_TYPES = {code for code, _label in PURCHASE_DOCUMENT_TYPES}


class TfDteClReceived(models.Model):
    _inherit = 'tf_dte_cl.received'

    def _tf_dte_cl_create_bill(self):
        result = super()._tf_dte_cl_create_bill()
        for received in self.filtered('move_id'):
            received.move_id.write({
                'tf_dte_cl_purchase_document_type': received.document_type if received.document_type in KNOWN_TYPES else 'other',
                'tf_dte_cl_purchase_folio': received.folio,
            })
        return result
