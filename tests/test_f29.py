# -*- coding: utf-8 -*-
"""Declaración F29 de un período completo, con el SII simulado. Ruta real: tests/test_f29.py"""
import base64

from odoo import Command
from odoo.tests import tagged

from odoo.addons.tf_dte_cl.tests.common import CUSTOMER_RUT
from odoo.addons.tf_dte_cl_intercambio.tests.common import SUPPLIER_RUT, IntercambioCommon

from .test_rules import purchases_csv, sales_csv


@tagged('post_install', '-at_install', 'tf_l10n_cl_f29')
class TestF29(IntercambioCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.tax_iva.tf_dte_cl_f29_category = 'iva_debit'
        cls.tax_iva_purchase.tf_dte_cl_f29_category = 'iva_credit'
        common = {'amount_type': 'percent', 'type_tax_use': 'purchase', 'tax_group_id': cls.tax_group_iva.id,
                  'company_id': cls.company.id, 'country_id': cls.chile.id}
        cls.tax_fixed_asset = env['account.tax'].create(dict(common, name='IVA activo fijo (prueba)', amount=19.0,
                                                             tf_dte_cl_f29_category='iva_fixed_asset'))
        cls.tax_fees = env['account.tax'].create(dict(common, name='Retención honorarios (prueba)', amount=-13.75,
                                                      tf_dte_cl_f29_category='withholding_fees'))
        cls.supplier = env['res.partner'].create({'name': 'Proveedor de Prueba SpA', 'vat': SUPPLIER_RUT,
                                                  'is_company': True, 'country_id': cls.chile.id})

    def sale(self, price):
        with self.fake_sii():
            move = self.create_invoice(quantity=1, price=price)
            move.action_post()
            move._tf_dte_cl_send()
            move._tf_dte_cl_query()
        return move

    def bill(self, price, tax, folio, doc_type='33'):
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.supplier.id, 'invoice_date': self.today,
            'tf_dte_cl_purchase_folio': folio,
            'invoice_line_ids': [Command.create({'name': 'Compra', 'quantity': 1, 'price_unit': price,
                                                 'tax_ids': [Command.set(tax.ids)]})],
        })
        bill.tf_dte_cl_purchase_document_type = doc_type
        bill.action_post()
        return bill

    def f29(self, year=None, month=None):
        return self.env['tf_l10n_cl.f29'].create({
            'year': year or self.today.year, 'month': str(month or self.today.month), 'ppm_rate': 0.2,
        })

    def period(self):
        first = self.sale(20000)                                  # IVA 3.800
        second = self.sale(10000)                                 # IVA 1.900
        with self.fake_sii():
            refund = second._reverse_moves([{'ref': 'Anula'}], cancel=False)
            refund.action_post()                                  # NC 61, IVA 1.900
        purchase = self.bill(50000, self.tax_iva_purchase, 100)  # crédito del giro 9.500
        asset = self.bill(200000, self.tax_fixed_asset, 101)     # activo fijo 38.000
        fees = self.bill(100000, self.tax_fees, 7, doc_type='bhe')  # retención 13.750
        self.env['account.payment.register'].with_context(active_model='account.move', active_ids=fees.ids) \
            .create({'payment_date': self.today})._create_payments()
        return first, second, refund, purchase, asset, fees

    def codes(self, declaration):
        return {line.code: line.value for line in declaration.line_ids}

    def test_period(self):
        first, second, refund, purchase, asset, _fees = self.period()
        declaration = self.f29()
        declaration.action_compute()
        c = self.codes(declaration)
        self.assertEqual((c['503'], c['502'], c['509'], c['510'], c['538']), (2, 5700, 1, 1900, 3800))
        self.assertEqual((c['519'], c['520'], c['524'], c['525']), (1, 9500, 1, 38000))
        self.assertEqual(c['537'], 47500)
        self.assertEqual((c['89'], c['77']), (0, 43700))
        self.assertEqual(c['151'], 13750)
        self.assertEqual(c['563'], 20000)                          # 20.000 + 10.000 − 10.000
        self.assertEqual(c['62'], 40)
        self.assertEqual(c['91'], 13790)
        self.assertEqual(declaration.total_to_pay, 13790)
        line_502 = declaration.line_ids.filtered(lambda l: l.code == '502')
        self.assertEqual(line_502.move_ids, first | second)

    def test_unpaid_fees_not_declared(self):
        self.bill(100000, self.tax_fees, 8, doc_type='bhe')
        declaration = self.f29()
        declaration.action_compute()
        self.assertEqual(self.codes(declaration)['151'], 0)

    def test_remainder_carried_to_next_month(self):
        self.period()
        declaration = self.f29()
        declaration.action_compute()
        year, month = (self.today.year, self.today.month + 1) if self.today.month < 12 else (self.today.year + 1, 1)
        following = self.f29(year, month)
        following.write({'utm_previous': 65000, 'utm_current': 65650})
        following.action_compute()
        self.assertEqual(following.previous_remainder, 43700)
        self.assertTrue(following.remainder_readjusted)
        self.assertEqual(self.codes(following)['504'], 44137)      # 43.700 × 65.650 / 65.000

    def test_presented_is_locked(self):
        declaration = self.f29()
        declaration.action_compute()
        declaration.action_present()
        with self.assertUserError('presentada'):
            declaration.action_compute()

    def test_rcv_comparison(self):
        first, second, refund, purchase, asset, _fees = self.period()
        declaration = self.f29()
        declaration.action_compute()
        wizard = self.env['tf_l10n_cl.f29.rcv.import'].create({
            'f29_id': declaration.id,
            'sales_file': base64.b64encode(sales_csv(
                ('33', CUSTOMER_RUT, first.tf_dte_cl_folio, 0, 20000, 3800, 23800),
                ('33', CUSTOMER_RUT, second.tf_dte_cl_folio, 0, 10000, 1900, 11900),
                ('61', CUSTOMER_RUT, refund.tf_dte_cl_folio, 0, 10000, 1900, 11900),
            )),
            'purchases_file': base64.b64encode(purchases_csv(
                ('33', SUPPLIER_RUT, 100, 0, 50000, 9500, 0, 59500, 0),
                ('33', SUPPLIER_RUT, 555, 0, 1000, 190, 0, 1190, 0),       # solo en el SII
            )),
        })
        wizard.action_import()
        status = {(c.kind, c.folio): c.status for c in declaration.comparison_ids}
        self.assertEqual(status[('sale', first.tf_dte_cl_folio)], 'match')
        self.assertEqual(status[('purchase', 100)], 'match')
        self.assertEqual(status[('purchase', 555)], 'missing_odoo')
        self.assertEqual(status[('purchase', 101)], 'missing_sii')      # activo fijo, no está en el RCV
        lines = {line.code: line for line in declaration.line_ids}
        self.assertEqual((lines['502'].rcv_value, lines['502'].difference), (5700, 0))
        self.assertEqual(lines['525'].difference, 38000)
