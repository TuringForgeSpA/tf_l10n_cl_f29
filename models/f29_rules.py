# -*- coding: utf-8 -*-
"""Reglas del F29 sin dependencias de Odoo: códigos, cálculo y lectura del RCV.

Ruta real: models/f29_rules.py

Fuente de los códigos: instrucciones oficiales del SII para llenar el
Formulario 29 (versión de noviembre de 2024).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

# Categoría F29 de cada impuesto.
CATEGORIES = [
    ('iva_debit', 'IVA débito fiscal (ventas)'),
    ('iva_credit', 'IVA crédito fiscal del giro (compras)'),
    ('iva_fixed_asset', 'IVA crédito fiscal activo fijo'),
    ('iva_supermarket', 'IVA crédito fiscal supermercados'),
    ('iva_no_credit', 'IVA sin derecho a crédito'),
    ('iva_common_use', 'IVA de uso común (proporcionalidad)'),
    ('withholding_fees', 'Retención de honorarios (Art. 42 N°2)'),
    ('unsupported', 'No soportado por el cálculo del F29'),
]

# Plantillas de impuestos de tf_l10n_cl (Chile TF) → categoría F29.
TEMPLATE_CATEGORIES = {
    'ITAX_19': 'iva_debit',
    'OTAX_19': 'iva_credit',
    'iva_activo_fijo': 'iva_fixed_asset',
    'iva_supermercado_recup': 'iva_supermarket',
    'iva_compra_no_recup': 'iva_no_credit',
    'iva_activo_fijo_uso_no_recup': 'iva_no_credit',
    'iva_compra_uso_comun': 'iva_common_use',
    'iva_activo_fijo_uso_comun': 'iva_common_use',
    'I_IU2C': 'withholding_fees',
    'I_IR2C_2021': 'withholding_fees',
    'I_IR2C_2022': 'withholding_fees',
    'I_IR2C_2023': 'withholding_fees',
    'I_IR2C_2024': 'withholding_fees',
    'I_IR2C_2025': 'withholding_fees',
    'I_IR2C_2026': 'withholding_fees',
    'I_RTI': 'unsupported',
    'especifico_compra': 'unsupported',
    'iec_gasoline': 'unsupported',
    'iec_diesel': 'unsupported',
    'ila_a_100_p': 'unsupported', 'ila_a_180_p': 'unsupported',
    'ila_v_205_p': 'unsupported', 'ila_l_315_p': 'unsupported',
    'ila_a_100_s': 'unsupported', 'ila_a_180_s': 'unsupported',
    'ila_v_205_s': 'unsupported', 'ila_l_315_s': 'unsupported', 'ila_c_205_s': 'unsupported',
}

# Códigos que calcula el módulo: (código, descripción, sección).
CODES = [
    ('586', 'Cantidad de documentos de ventas exentas', 'ventas'),
    ('142', 'Monto neto de ventas exentas', 'ventas'),
    ('503', 'Cantidad de facturas emitidas', 'debitos'),
    ('502', 'Débito fiscal de facturas emitidas', 'debitos'),
    ('512', 'Cantidad de notas de débito emitidas', 'debitos'),
    ('513', 'Débito fiscal de notas de débito emitidas', 'debitos'),
    ('509', 'Cantidad de notas de crédito emitidas', 'debitos'),
    ('510', 'Débito fiscal de notas de crédito emitidas (resta)', 'debitos'),
    ('538', 'Total débitos', 'debitos'),
    ('564', 'Cantidad de compras internas afectas sin derecho a crédito', 'compras'),
    ('521', 'Monto neto de compras internas afectas sin derecho a crédito', 'compras'),
    ('584', 'Cantidad de compras exentas o no gravadas', 'compras'),
    ('562', 'Monto neto de compras exentas o no gravadas', 'compras'),
    ('519', 'Cantidad de facturas recibidas del giro', 'creditos'),
    ('520', 'Crédito fiscal de facturas recibidas del giro', 'creditos'),
    ('761', 'Cantidad de facturas de supermercados', 'creditos'),
    ('762', 'Crédito fiscal de facturas de supermercados', 'creditos'),
    ('524', 'Cantidad de facturas de activo fijo', 'creditos'),
    ('525', 'Crédito fiscal de facturas de activo fijo', 'creditos'),
    ('527', 'Cantidad de notas de crédito recibidas', 'creditos'),
    ('528', 'Crédito fiscal de notas de crédito recibidas (resta)', 'creditos'),
    ('531', 'Cantidad de notas de débito recibidas', 'creditos'),
    ('532', 'Crédito fiscal de notas de débito recibidas', 'creditos'),
    ('504', 'Remanente de crédito fiscal del mes anterior (reajustado)', 'creditos'),
    ('537', 'Total créditos', 'creditos'),
    ('89', 'IVA determinado', 'resultado'),
    ('77', 'Remanente de crédito fiscal para el período siguiente', 'resultado'),
    ('151', 'Retención de honorarios (Art. 42 N°2 LIR)', 'renta'),
    ('563', 'PPM: base imponible (ingresos brutos)', 'renta'),
    ('115', 'PPM: tasa (%)', 'renta'),
    ('68', 'PPM: crédito (PPV imputado)', 'renta'),
    ('62', 'PPM neto determinado', 'renta'),
    ('595', 'Subtotal impuesto determinado', 'total'),
    ('91', 'Total a pagar dentro del plazo legal', 'total'),
]
CODE_NAMES = {code: name for code, name, _section in CODES}
SALE_DOCUMENT_TYPES = ('33', '34', '56', '61')
PURCHASE_DOCUMENT_TYPES = [
    ('33', 'Factura electrónica (33)'),
    ('34', 'Factura exenta electrónica (34)'),
    ('46', 'Factura de compra electrónica (46)'),
    ('56', 'Nota de débito electrónica (56)'),
    ('61', 'Nota de crédito electrónica (61)'),
    ('30', 'Factura en papel (30)'),
    ('32', 'Factura exenta en papel (32)'),
    ('55', 'Nota de débito en papel (55)'),
    ('60', 'Nota de crédito en papel (60)'),
    ('bhe', 'Boleta de honorarios electrónica'),
    ('other', 'Otro (no se declara en el F29)'),
]
PURCHASE_INVOICE_TYPES = ('30', '33', '46')
PURCHASE_EXEMPT_TYPES = ('32', '34')
PURCHASE_DEBIT_TYPES = ('55', '56')
PURCHASE_CREDIT_TYPES = ('60', '61')


def round_peso(value) -> int:
    return int(Decimal(str(value or 0)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def category_from_xmlid(xmlid: str | None) -> str | bool:
    """Categoría de un impuesto de tf_l10n_cl a partir de su xmlid (``account.<cía>_<plantilla>``)."""
    if not xmlid or '.' not in xmlid:
        return False
    name = xmlid.split('.', 1)[1]
    template = name.split('_', 1)[1] if '_' in name and name.split('_', 1)[0].isdigit() else name
    return TEMPLATE_CATEGORIES.get(template, False)


def readjusted_remainder(previous: int, utm_previous: float, utm_current: float) -> tuple[int, bool]:
    """Código 504: remanente anterior reajustado por la variación de la UTM (Art. 27 D.L. 825).

    Devuelve (monto, reajustado). Sin los dos valores de UTM se usa el monto nominal.
    """
    if previous and utm_previous and utm_current:
        return round_peso(Decimal(str(previous)) * Decimal(str(utm_current)) / Decimal(str(utm_previous))), True
    return round_peso(previous), False


@dataclass
class SaleDoc:
    doc_type: str
    net: int = 0          # neto afecto
    exempt: int = 0
    iva: int = 0
    ref: object = None    # identificador del documento (id del asiento en Odoo)


@dataclass
class PurchaseDoc:
    doc_type: str
    net: int = 0
    exempt: int = 0
    iva_credit: int = 0
    iva_fixed_asset: int = 0
    iva_supermarket: int = 0
    no_credit_base: int = 0
    ref: object = None


def compute_codes(sales: list[SaleDoc], purchases: list[PurchaseDoc], fees: int, remainder: int,
                  ppm_rate: float, ppv_credit: int, documents: dict | None = None) -> dict[str, float]:
    """Códigos del F29 a partir de los documentos del período.

    Si se entrega ``documents`` (dict), se llena con código → lista de ``ref`` de los
    documentos que forman cada código de cantidad y de monto.
    """
    c = {code: 0 for code, _name, _section in CODES}
    docs = documents if documents is not None else {}

    def add(count_code, amount_code, amount, doc):
        c[count_code] += 1
        c[amount_code] += amount
        for code in (count_code, amount_code):
            docs.setdefault(code, []).append(doc.ref)

    for doc in sales:
        if doc.doc_type == '34':
            add('586', '142', doc.exempt, doc)
        elif doc.doc_type == '33':
            add('503', '502', doc.iva, doc)
        elif doc.doc_type == '56':
            add('512', '513', doc.iva, doc)
        elif doc.doc_type == '61':
            add('509', '510', doc.iva, doc)
    c['538'] = c['502'] + c['513'] - c['510']
    for doc in purchases:
        credit = doc.iva_credit + doc.iva_fixed_asset + doc.iva_supermarket
        if doc.no_credit_base:
            add('564', '521', doc.no_credit_base, doc)
        if doc.doc_type in PURCHASE_EXEMPT_TYPES:
            add('584', '562', doc.exempt, doc)
        elif doc.doc_type in PURCHASE_CREDIT_TYPES:
            if credit:
                add('527', '528', credit, doc)
        elif doc.doc_type in PURCHASE_DEBIT_TYPES:
            if credit:
                add('531', '532', credit, doc)
        elif doc.doc_type in PURCHASE_INVOICE_TYPES:
            if doc.iva_credit:
                add('519', '520', doc.iva_credit, doc)
            if doc.iva_supermarket:
                add('761', '762', doc.iva_supermarket, doc)
            if doc.iva_fixed_asset:
                add('524', '525', doc.iva_fixed_asset, doc)
    c['504'] = remainder
    c['537'] = c['520'] + c['762'] + c['525'] - c['528'] + c['532'] + c['504']
    difference = c['538'] - c['537']
    c['89'] = max(difference, 0)
    c['77'] = max(-difference, 0)
    c['151'] = fees
    c['563'] = sum(d.net + d.exempt for d in sales if d.doc_type in ('33', '34', '56')) \
        - sum(d.net + d.exempt for d in sales if d.doc_type == '61')
    c['115'] = ppm_rate
    c['68'] = ppv_credit
    c['62'] = max(round_peso(Decimal(str(max(c['563'], 0))) * Decimal(str(ppm_rate)) / 100) - ppv_credit, 0)
    c['595'] = c['89'] + c['151'] + c['62']
    c['91'] = c['595']
    return c


# ----------------------------------------------------------------------
# Registro de Compras y Ventas (RCV): archivos descargados del SII
# ----------------------------------------------------------------------
@dataclass
class RcvRow:
    kind: str                 # 'sale' | 'purchase'
    doc_type: str
    rut: str
    name: str
    folio: int
    date: date | None
    exempt: int = 0
    net: int = 0
    iva: int = 0              # ventas: IVA; compras: IVA recuperable
    iva_no_credit: int = 0
    iva_fixed_asset: int = 0
    iva_common_use: int = 0
    total: int = 0
    extra: dict = field(default_factory=dict)


SALE_COLUMNS = {'Tipo Doc', 'Rut cliente', 'Folio', 'Fecha Docto', 'Monto Exento', 'Monto Neto', 'Monto IVA', 'Monto total'}
PURCHASE_COLUMNS = {'Tipo Doc', 'RUT Proveedor', 'Folio', 'Fecha Docto', 'Monto Exento', 'Monto Neto',
                    'Monto IVA Recuperable', 'Monto Iva No Recuperable', 'Monto Total', 'IVA Activo Fijo', 'IVA uso Comun'}


def _decode(raw: bytes) -> str:
    for encoding in ('utf-8-sig', 'ISO-8859-1'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def _int(value) -> int:
    text = str(value or '').strip().replace('.', '').replace(',', '.')
    try:
        return round_peso(text) if text else 0
    except Exception:  # noqa: BLE001 - valor no numérico: se informa como cero
        return 0


def _date(value) -> date | None:
    text = str(value or '').strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def parse_rcv(raw: bytes) -> tuple[str, list[RcvRow]]:
    """Lee un detalle del RCV (ventas o compras) descargado del SII. Separador: punto y coma."""
    text = _decode(raw)
    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    headers = {h.strip() for h in (reader.fieldnames or []) if h}
    if SALE_COLUMNS <= headers:
        kind = 'sale'
    elif PURCHASE_COLUMNS <= headers:
        kind = 'purchase'
    else:
        raise ValueError('El archivo no tiene las columnas del detalle de ventas o de compras del RCV.')
    rows = []
    for record in reader:
        record = {(k or '').strip(): (v or '').strip() for k, v in record.items()}
        if not record.get('Tipo Doc') or not record.get('Folio'):
            continue
        if kind == 'sale':
            row = RcvRow('sale', record['Tipo Doc'], record['Rut cliente'].upper(), record.get('Razon Social', ''),
                         _int(record['Folio']), _date(record['Fecha Docto']),
                         exempt=_int(record['Monto Exento']), net=_int(record['Monto Neto']),
                         iva=_int(record['Monto IVA']), total=_int(record['Monto total']))
        else:
            row = RcvRow('purchase', record['Tipo Doc'], record['RUT Proveedor'].upper(), record.get('Razon Social', ''),
                         _int(record['Folio']), _date(record['Fecha Docto']),
                         exempt=_int(record['Monto Exento']), net=_int(record['Monto Neto']),
                         iva=_int(record['Monto IVA Recuperable']),
                         iva_no_credit=_int(record['Monto Iva No Recuperable']),
                         iva_fixed_asset=_int(record['IVA Activo Fijo']),
                         iva_common_use=_int(record['IVA uso Comun']), total=_int(record['Monto Total']),
                         extra={'tipo_compra': record.get('Tipo Compra', '')})
        rows.append(row)
    return kind, rows


def rcv_codes(rows: list[RcvRow]) -> dict[str, int]:
    """Códigos del F29 que se derivan del RCV, para compararlos con los calculados en Odoo."""
    c = {code: 0 for code in ('586', '142', '503', '502', '512', '513', '509', '510',
                              '564', '521', '584', '562', '519', '520', '524', '525',
                              '527', '528', '531', '532')}
    for row in rows:
        if row.kind == 'sale':
            if row.doc_type == '34':
                c['586'] += 1
                c['142'] += row.exempt
            elif row.doc_type == '33':
                c['503'] += 1
                c['502'] += row.iva
            elif row.doc_type == '56':
                c['512'] += 1
                c['513'] += row.iva
            elif row.doc_type == '61':
                c['509'] += 1
                c['510'] += row.iva
            continue
        if row.iva_no_credit:
            c['564'] += 1
            c['521'] += row.net
        if row.doc_type in PURCHASE_EXEMPT_TYPES:
            c['584'] += 1
            c['562'] += row.exempt
        elif row.doc_type in PURCHASE_CREDIT_TYPES:
            if row.iva or row.iva_fixed_asset:
                c['527'] += 1
                c['528'] += row.iva + row.iva_fixed_asset
        elif row.doc_type in PURCHASE_DEBIT_TYPES:
            if row.iva or row.iva_fixed_asset:
                c['531'] += 1
                c['532'] += row.iva + row.iva_fixed_asset
        elif row.doc_type in PURCHASE_INVOICE_TYPES:
            if row.iva:
                c['519'] += 1
                c['520'] += row.iva
            if row.iva_fixed_asset:
                c['524'] += 1
                c['525'] += row.iva_fixed_asset
    return c


def compare_documents(odoo: dict, rcv: dict) -> list[dict]:
    """Compara documentos por clave (tipo, tipo DTE, RUT, folio) → {total, iva}."""
    result = []
    for key in sorted(set(odoo) | set(rcv), key=lambda k: (k[0], k[1], k[2], k[3])):
        mine, theirs = odoo.get(key), rcv.get(key)
        if mine and not theirs:
            status = 'missing_sii'
        elif theirs and not mine:
            status = 'missing_odoo'
        elif mine['total'] != theirs['total'] or mine['iva'] != theirs['iva']:
            status = 'difference'
        else:
            status = 'match'
        result.append({
            'kind': key[0], 'doc_type': key[1], 'rut': key[2], 'folio': key[3], 'status': status,
            'odoo_total': (mine or {}).get('total', 0), 'sii_total': (theirs or {}).get('total', 0),
            'odoo_iva': (mine or {}).get('iva', 0), 'sii_iva': (theirs or {}).get('iva', 0),
        })
    return result
