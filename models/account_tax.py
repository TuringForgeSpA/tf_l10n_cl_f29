# -*- coding: utf-8 -*-
"""Categoría F29 de cada impuesto.

Ruta real: models/account_tax.py
"""
from odoo import fields, models

from .f29_rules import CATEGORIES, category_from_xmlid


class AccountTax(models.Model):
    _inherit = 'account.tax'

    tf_dte_cl_f29_category = fields.Selection(
        CATEGORIES, string='Categoría F29',
        help='Cómo se declara este impuesto en el F29. Para los impuestos del plan "Chile (TF)" se '
             'asigna sola; para otros, elíjala aquí.',
    )

    def _tf_dte_cl_f29_resolved_category(self):
        """La categoría elegida o, si no hay, la que corresponde a su plantilla de tf_l10n_cl."""
        self.ensure_one()
        if self.tf_dte_cl_f29_category:
            return self.tf_dte_cl_f29_category
        category = category_from_xmlid(self.get_external_id().get(self.id))
        if category:
            self.sudo().tf_dte_cl_f29_category = category
        return category
