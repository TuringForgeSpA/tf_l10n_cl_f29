# -*- coding: utf-8 -*-
"""Ruta real: hooks.py"""


def post_init_hook(env):
    """Asigna la categoría F29 a los impuestos existentes del plan "Chile (TF)"."""
    for tax in env['account.tax'].with_context(active_test=False).search([('tf_dte_cl_f29_category', '=', False)]):
        tax._tf_dte_cl_f29_resolved_category()
