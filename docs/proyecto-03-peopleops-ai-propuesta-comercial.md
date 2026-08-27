# PeopleOps AI
## Copiloto inteligente de Recursos Humanos para datos, políticas y payroll

### Una nueva forma de consultar y entender la información de RRHH

PeopleOps AI es una solución de inteligencia artificial diseñada para ayudar a los equipos de Recursos Humanos a consultar, analizar y relacionar información que hoy suele estar dispersa entre el ERP, payroll, asistencia, contratos, vacaciones y documentos internos.

La idea es simple:

> **preguntar en lenguaje natural y recibir una respuesta explicada, sustentada por datos y políticas.**

---

## El problema

En muchas empresas, responder preguntas de RRHH requiere:

- entrar a varias pantallas del ERP;
- buscar reportes;
- pedir ayuda a TI;
- revisar hojas de cálculo;
- consultar manualmente políticas;
- comparar períodos de payroll;
- revisar asistencia y horas extra;
- validar excepciones con varias personas.

Esto consume tiempo y hace que el conocimiento dependa demasiado de usuarios expertos.

---

## Qué propone PeopleOps AI

PeopleOps AI funciona como un **copiloto de RRHH**.

El usuario puede preguntar, por ejemplo:

> “¿Qué contratos vencen en los próximos 45 días?”

> “¿Qué empleados tienen vacaciones pendientes?”

> “¿Por qué este trabajador recibió menos neto este mes?”

> “¿Las horas extra pagadas coinciden con las registradas?”

> “¿Qué política regula esta solicitud?”

> “¿Puede este empleado solicitar 15 días de vacaciones en noviembre?”

La aplicación combina la información disponible y explica qué encontró.

---

## No reemplaza su ERP

PeopleOps AI está pensado para trabajar **encima del ERP/HRIS existente**, no para reemplazarlo.

La solución se conecta mediante una capa de integración estándar basada en MCP.

Esto permite que PeopleOps AI pueda adaptarse a distintos sistemas sin depender de un único proveedor o modelo de base de datos.

Para una empresa, esto significa:

- conservar su ERP actual;
- aprovechar sus datos existentes;
- evitar una migración completa;
- agregar una nueva capa de inteligencia.

---

## La integración se adapta a su realidad

Cada ERP puede tener:

- tablas diferentes;
- desarrollos propios;
- nombres distintos;
- Oracle, SQL Server, PostgreSQL u otro DBMS;
- reglas particulares.

PeopleOps AI no obliga a cambiar ese modelo.

El componente de integración conoce el sistema del cliente, descubre qué información existe y la presenta a PeopleOps de forma controlada.

Esto permite que el producto principal sea reutilizable y que la integración se adapte a cada empresa.

---

## Payroll con más contexto

PeopleOps AI no se limita a mostrar el total de nómina.

Puede ayudar a responder preguntas como:

- ¿qué concepto cambió?;
- ¿qué descuento explica una diferencia?;
- ¿cuántas horas extra se registraron?;
- ¿cuántas fueron pagadas?;
- ¿qué empleados presentan diferencias entre asistencia y payroll?;
- ¿qué cambió respecto al período anterior?

Esto permite investigar incidencias con mayor rapidez.

---

## Políticas y procedimientos disponibles desde el mismo lugar

PeopleOps AI incorpora una base de conocimiento de Recursos Humanos.

La empresa puede cargar:

- políticas de vacaciones;
- asistencia;
- horas extra;
- trabajo remoto;
- permisos;
- procedimientos de payroll;
- renovación de contratos;
- matrices de aprobación;
- otros documentos internos.

La solución conserva versiones y puede utilizar la política aplicable al período consultado.

La respuesta muestra evidencia para que el usuario pueda verificarla.

---

## Human-in-the-loop

PeopleOps AI está diseñado para **apoyar decisiones**, no para reemplazar al responsable de RRHH.

Cuando una situación es ambigua, sensible o requiere autorización, el sistema puede derivarla a revisión humana.

Ejemplo:

```text
Solicitud
   ↓
Datos del empleado
   +
Política vigente
   ↓
Análisis
   ↓
Requiere revisión
   ↓
Responsable de RRHH
```

Esto permite utilizar IA manteniendo control y trazabilidad.

---

## Ejemplos de uso

### Vacaciones
“¿Puede este empleado solicitar 15 días en noviembre?”

La aplicación puede revisar:

- saldo;
- solicitudes existentes;
- contrato;
- política vigente;
- restricciones;
- excepciones.

### Payroll
“¿Por qué recibió menos neto este mes?”

Puede comparar:

- nómina actual;
- nómina anterior;
- conceptos;
- descuentos;
- horas extra;
- asistencia;
- permisos.

### Contratos
“¿Qué contratos vencen en los próximos 60 días y además tienen vacaciones pendientes?”

Puede combinar datos que normalmente se revisarían por separado.

---

## Qué recibe la empresa

Una implementación puede incluir:

- PeopleOps AI;
- interfaz web;
- integración con el ERP/HRIS;
- carga de políticas;
- configuración de permisos;
- análisis de payroll;
- workflows de revisión;
- auditoría;
- capacitación.

---

## Beneficios esperados

- consultas más rápidas;
- menor dependencia de TI;
- mejor acceso a políticas;
- investigación más sencilla de payroll;
- reducción de trabajo manual;
- más trazabilidad;
- mejor aprovechamiento del ERP existente;
- posibilidad de ampliar nuevos casos de uso posteriormente.

---

## Seguridad y control

La solución está diseñada con principios de:

- acceso de solo lectura para análisis;
- mínimos privilegios;
- trazabilidad;
- restricciones específicas para payroll;
- evidencia;
- revisión humana;
- separación entre datos del ERP y conocimiento documental.

En una implementación real, los permisos se configuran de acuerdo con las políticas de la organización.

---

## Una solución que puede crecer

PeopleOps AI puede comenzar con casos concretos:

1. contratos;
2. asistencia;
3. vacaciones;
4. payroll;
5. políticas.

Después pueden incorporarse nuevos procesos sin cambiar la idea central de la solución.

---

## Propuesta de piloto

Una forma práctica de iniciar es con un piloto controlado:

### Fase 1
Conectar un entorno autorizado del ERP/HRIS.

### Fase 2
Cargar políticas y procedimientos seleccionados.

### Fase 3
Validar preguntas reales de RRHH.

### Fase 4
Comparar resultados con el proceso actual.

### Fase 5
Definir qué casos generan mayor valor y ampliar el alcance.

---

## Resultado esperado del piloto

Al finalizar, la empresa debería poder evaluar con datos reales:

- qué preguntas puede resolver;
- cuánto tiempo reduce;
- qué calidad tienen las respuestas;
- qué procesos conviene incorporar;
- qué controles adicionales necesita.

---

## Visión

PeopleOps AI busca transformar el ERP de Recursos Humanos de un sistema que principalmente **almacena información** en una plataforma sobre la que también se puede **preguntar, investigar y razonar**.

> **Los datos siguen en su sistema.  
> Las políticas siguen bajo su control.  
> PeopleOps AI agrega una capa de inteligencia sobre ambos.**
