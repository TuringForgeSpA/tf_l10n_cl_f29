# Manual de uso — Apoyo para el F29 (tf_l10n_cl_f29)

## 1. Antes de empezar

- **Impuestos:** con el plan «Chile (TF)» no hay que hacer nada. Con otro plan, en
  *Contabilidad > Configuración > Impuestos* asigna a cada impuesto su
  **Categoría F29** (IVA débito, IVA crédito del giro, activo fijo, etc.).
- **Facturas de proveedor:** revisa que tengan **Tipo de documento SII (compra)**
  y **Folio del proveedor**. Las creadas desde *Documentos recibidos* ya los
  traen. Las boletas de honorarios van como *Boleta de honorarios electrónica*,
  con el impuesto de retención.

## 2. Calcular la declaración

1. *Contabilidad > Informes > Declaraciones F29*, **Nuevo**.
2. Elige el **mes y el año**. Revisa la **tasa de PPM** (se propone la del mes
   anterior) y el **crédito PPV**, si corresponde.
3. **Remanente:** si el F29 del mes anterior está en Odoo, se toma solo. Ingresa
   la **UTM** del mes anterior y la del período para reajustarlo; si no, se usa
   el monto nominal y la declaración lo advierte.
4. Usa **Calcular**. Cada código muestra su valor, y el ícono de lista abre los
   documentos que lo forman.

Revisa los **avisos** en la parte superior: indican documentos o impuestos que
el cálculo no incluye y que debes completar a mano.

## 3. Comparar con el SII

1. En el sitio del SII, *Registro de Compras y Ventas*, elige el período y
   descarga el **detalle** de ventas y de compras.
2. En la declaración, usa **Comparar con el RCV** y carga los archivos sin
   modificarlos.
3. La pestaña **Comparación con el RCV** muestra cada documento:

| Resultado | Qué hacer |
|---|---|
| Solo en el SII | Falta registrarlo en Odoo (típicamente, una factura de proveedor) |
| Solo en Odoo | Revisa el tipo, el folio o el RUT; o el SII aún no lo registra |
| Montos distintos | Compara los montos de la factura en Odoo con el documento |

En la pestaña **Códigos**, las columnas *RCV del SII* y *Diferencia* muestran
cada código según el RCV; los que difieren aparecen en rojo.

## 4. Presentar

Completa el F29 en el sitio del SII con los valores propuestos, y luego usa
**Marcar como presentada** para bloquear la declaración. Su código 77 será el
remanente del mes siguiente.
