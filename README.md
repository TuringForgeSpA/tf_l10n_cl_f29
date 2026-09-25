# tf_l10n_cl_f29

Apoyo para la declaración mensual **F29** en Odoo 18: calcula los códigos desde
las facturas de venta y de proveedor, y los compara con el **Registro de Compras
y Ventas (RCV)** del SII. Depende de `tf_l10n_cl` y `tf_dte_cl_intercambio`.
Versión 18.0.1.0.0.

Fuente de los códigos: instrucciones oficiales del SII para llenar el F29
(versión de noviembre de 2024). El módulo **no presenta** el F29: propone los
valores para completarlo en el sitio del SII.

## Códigos que calcula

| Sección | Códigos |
|---|---|
| Ventas exentas | 586, 142 (facturas exentas 34) |
| Débitos | 503/502 (facturas), 512/513 (notas de débito), 509/510 (notas de crédito), 538 |
| Compras sin crédito | 564/521 (IVA no recuperable), 584/562 (compras exentas) |
| Créditos | 519/520 (giro), 761/762 (supermercados), 524/525 (activo fijo), 527/528 (NC recibidas), 531/532 (ND recibidas), 504 (remanente reajustado), 537 |
| Resultado | 89 (IVA determinado) o 77 (remanente) |
| Renta | 151 (retención de honorarios, según fecha de pago), 563/115/68/62 (PPM) |
| Total | 595, 91 |

## Cómo clasifica

- **Ventas:** facturas y notas emitidas con DTE, por tipo (33, 34, 56, 61) y
  fecha de factura, con los mismos montos que el DTE.
- **Compras:** facturas de proveedor por **Tipo de documento SII (compra)** y
  fecha contable. Las creadas desde *Documentos recibidos* lo traen, junto con el
  folio; en las demás se elige en la factura.
- **Impuestos:** cada impuesto tiene una **Categoría F29**. Para el plan
  «Chile (TF)» se asigna sola desde su plantilla; para otros, se elige en el
  impuesto.
- **Honorarios (151):** la retención se declara el mes siguiente al **pago**, así
  que se toma la parte pagada dentro del período.
- **Remanente (504):** el código 77 del F29 anterior, reajustado por la variación
  de la UTM entre ambos meses (Art. 27 D.L. 825), si se ingresan los dos valores.

**No calcula** (lo advierte en la declaración): IVA de uso común
(proporcionalidad), impuestos adicionales (ILA), impuestos a combustibles,
cambio de sujeto y exportaciones.

## Comparación con el RCV

Se cargan los **detalles** de ventas y de compras descargados del RCV (CSV
separado por punto y coma, tal como los entrega el SII). El módulo compara
documento por documento (solo en el SII, solo en Odoo, montos distintos) y cada
código con su valor según el RCV.

## Pruebas

```bash
./odoo-bin -c /etc/odoo.conf -d odoo_tests --without-demo=all \
    -i tf_l10n_cl_f29 --test-enable --test-tags /tf_l10n_cl_f29 \
    --http-port=8070 --logfile=/tmp/odoo_tests.log --stop-after-init
```

© 2026 Turing Forge SpA. Distribuido bajo LGPL-3; vea los archivos `LICENSE` (LGPL-3) y `LICENSE.GPL` (GPL-3).
