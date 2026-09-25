# -*- coding: utf-8 -*-
{
    'name': 'Chile - Apoyo para el F29',
    'summary': 'Calcula los códigos del F29 desde Odoo y los compara con el Registro de Compras y Ventas del SII.',
    'description': 'Declaración mensual F29: IVA, retenciones de honorarios y PPM, con comparación contra el RCV. '
                   'Ver README.md para la documentación completa.',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Localizations/Reporting',
    'license': 'LGPL-3',
    'author': 'TF',
    'depends': [
        'tf_l10n_cl',
        'tf_dte_cl_intercambio',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/f29_views.xml',
        'views/account_views.xml',
        'wizard/rcv_import_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
