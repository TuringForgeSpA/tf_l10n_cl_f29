# -*- coding: utf-8 -*-
"""Reglas del F29 sin base de datos. Ruta real: tests/test_rules.py"""
from odoo.tests import TransactionCase, tagged

from odoo.addons.tf_l10n_cl_f29.models import f29_rules as r

SALES_HEADER = ('Nro;Tipo Doc;Tipo Venta;Rut cliente;Razon Social;Folio;Fecha Docto;Fecha Recepcion;Fecha Acuse Recibo;'
                'Fecha Reclamo;Monto Exento;Monto Neto;Monto IVA;Monto total;IVA Retenido Total;IVA Retenido Parcial;'
                'IVA no retenido;IVA propio;IVA Terceros;RUT Emisor Liquid. Factura;Neto Comision Liquid. Factura;'
                'Exento Comision Liquid. Factura;IVA Comision Liquid. Factura;IVA fuera de plazo;Tipo Docto. Referencia;'
                'Folio Docto. Referencia;Num. Ident. Receptor Extranjero;Nacionalidad Receptor Extranjero;'
                'Credito empresa constructora;Impto. Zona Franca (Ley 18211);Garantia Dep. Envases;'
                'Indicador Venta sin Costo;Indicador Servicio Periodico;Monto No facturable;Total Monto Periodo;'
                'Venta Pasajes Transporte Nacional;Venta Pasajes Transporte Internacional;Numero Interno;'
                'Codigo Sucursal;NCE o NDE sobre Fact. de Compra;Codigo Otro Imp.;Valor Otro Imp.;Tasa Otro Imp.')
PURCHASES_HEADER = ('Nro;Tipo Doc;Tipo Compra;RUT Proveedor;Razon Social;Folio;Fecha Docto;Fecha Recepcion;Fecha Acuse;'
                    'Monto Exento;Monto Neto;Monto IVA Recuperable;Monto Iva No Recuperable;Codigo IVA No Rec.;'
                    'Monto Total;Monto Neto Activo Fijo;IVA Activo Fijo;IVA uso Comun;Impto. Sin Derecho a Credito;'
                    'IVA No Retenido;Tabacos Puros;Tabacos Cigarrillos;Tabacos Elaborados;'
                    'NCE o NDE sobre Fact. de Compra;Codigo Otro Impuesto;Valor Otro Impuesto;Tasa Otro Impuesto')


def sales_csv(*rows):
    """rows: (tipo, rut, folio, exento, neto, iva, total)."""
    lines = [SALES_HEADER]
    for i, (doc_type, rut, folio, exempt, net, iva, total) in enumerate(rows, start=1):
        lines.append(';'.join([str(i), doc_type, 'Del Giro', rut, 'Cliente', str(folio), '01/09/2026', '', '', '',
                               str(exempt), str(net), str(iva), str(total)] + [''] * 29))
    return '\n'.join(lines).encode('ISO-8859-1')


def purchases_csv(*rows):
    """rows: (tipo, rut, folio, exento, neto, iva, iva_no_rec, total, iva_activo_fijo)."""
    lines = [PURCHASES_HEADER]
    for i, (doc_type, rut, folio, exempt, net, iva, no_rec, total, fixed) in enumerate(rows, start=1):
        lines.append(';'.join([str(i), doc_type, 'Del Giro', rut, 'Proveedor', str(folio), '01/09/2026', '', '',
                               str(exempt), str(net), str(iva), str(no_rec), '', str(total), '0', str(fixed), '0']
                              + [''] * 9))
    return '\n'.join(lines).encode('ISO-8859-1')


@tagged('post_install', '-at_install', 'tf_l10n_cl_f29')
class TestF29Rules(TransactionCase):

    def test_categories_from_template(self):
        self.assertEqual(r.category_from_xmlid('account.1_OTAX_19'), 'iva_credit')
        self.assertEqual(r.category_from_xmlid('account.12_I_IR2C_2024'), 'withholding_fees')
        self.assertEqual(r.category_from_xmlid('account.1_iva_activo_fijo'), 'iva_fixed_asset')
        self.assertFalse(r.category_from_xmlid('account.1_OTRO'))
        self.assertFalse(r.category_from_xmlid(None))

    def test_readjusted_remainder(self):
        self.assertEqual(r.readjusted_remainder(100000, 65000, 65650), (101000, True))
        self.assertEqual(r.readjusted_remainder(100000, 0, 65650), (100000, False))

    def test_codes(self):
        sales = [r.SaleDoc('33', net=100000, iva=19000), r.SaleDoc('34', exempt=30000),
                 r.SaleDoc('61', net=10000, iva=1900), r.SaleDoc('56', net=5000, iva=950)]
        purchases = [r.PurchaseDoc('33', net=40000, iva_credit=7600), r.PurchaseDoc('33', iva_fixed_asset=38000),
                     r.PurchaseDoc('33', iva_supermarket=1900), r.PurchaseDoc('61', iva_credit=380),
                     r.PurchaseDoc('34', exempt=15000), r.PurchaseDoc('33', no_credit_base=8000)]
        c = r.compute_codes(sales, purchases, fees=13750, remainder=5000, ppm_rate=0.2, ppv_credit=0)
        self.assertEqual((c['503'], c['502'], c['586'], c['142']), (1, 19000, 1, 30000))
        self.assertEqual(c['538'], 19000 + 950 - 1900)
        self.assertEqual((c['520'], c['525'], c['762'], c['528'], c['562'], c['521']),
                         (7600, 38000, 1900, 380, 15000, 8000))
        self.assertEqual(c['537'], 7600 + 1900 + 38000 - 380 + 5000)
        self.assertEqual((c['89'], c['77']), (0, 52120 - 18050))
        self.assertEqual(c['563'], 100000 + 30000 + 5000 - 10000)
        self.assertEqual(c['62'], 250)                               # 0,2 % de 125.000
        self.assertEqual(c['91'], 13750 + 250)

    def test_parse_rcv(self):
        kind, rows = r.parse_rcv(sales_csv(('33', '76323752-4', 12, 0, 100000, 19000, 119000)))
        self.assertEqual((kind, rows[0].folio, rows[0].iva, rows[0].total), ('sale', 12, 19000, 119000))
        kind, rows = r.parse_rcv(purchases_csv(('33', '96806980-2', 54346541, 0, 6602, 1254, 0, 7856, 0)))
        self.assertEqual((kind, rows[0].folio, rows[0].iva), ('purchase', 54346541, 1254))
        with self.assertRaises(ValueError):
            r.parse_rcv(b'a;b;c\n1;2;3')

    def test_compare(self):
        result = r.compare_documents(
            {('sale', '33', '1-9', 1): {'total': 10, 'iva': 1}, ('sale', '33', '1-9', 2): {'total': 5, 'iva': 0}},
            {('sale', '33', '1-9', 1): {'total': 10, 'iva': 1}, ('sale', '33', '1-9', 3): {'total': 7, 'iva': 0}})
        self.assertEqual({(x['folio'], x['status']) for x in result},
                         {(1, 'match'), (2, 'missing_sii'), (3, 'missing_odoo')})


@tagged('post_install', '-at_install', 'tf_l10n_cl_f29')
class TestF29TemplateCategories(TransactionCase):

    def test_template_taxes_exist(self):
        """Cada impuesto que el F29 clasifica por plantilla debe existir en "Chile (TF)"."""
        template_taxes = set(self.env['account.chart.template']._get_chart_template_data('cl_tf')['account.tax'])
        missing = set(r.TEMPLATE_CATEGORIES) - template_taxes
        self.assertFalse(missing, 'Plantillas de impuestos que ya no existen en tf_l10n_cl: %s' % sorted(missing))
        unclassified = template_taxes - set(r.TEMPLATE_CATEGORIES)
        self.assertFalse(unclassified, 'Impuestos de "Chile (TF)" sin categoría F29: %s' % sorted(unclassified))
