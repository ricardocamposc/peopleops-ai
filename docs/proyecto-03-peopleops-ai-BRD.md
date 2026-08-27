# Proyecto 03 — PeopleOps AI — HR Intelligence Copilot
## Business Requirements Document (BRD)

**Estado:** Definición inicial cerrada  
**Versión:** 1.0  
**Documento:** Requisitos de negocio

---

## 1. Resumen ejecutivo

PeopleOps AI busca convertir información dispersa de Recursos Humanos —empleados, contratos, asistencia, vacaciones, horas extra, payroll, políticas y procedimientos— en una capacidad de consulta y análisis accesible mediante lenguaje natural.

El problema de negocio no es únicamente “buscar información”. En RRHH, una respuesta útil suele requerir combinar datos estructurados con reglas documentadas y, en situaciones sensibles, conservar revisión humana.

PeopleOps AI propone una experiencia donde el usuario pueda preguntar, investigar y comprender situaciones laborales sin conocer tablas, SQL ni la ubicación exacta de cada política.

El producto debe poder conectarse a distintos ERP/HRIS sin quedar atado a un modelo de datos concreto.

---

## 2. Problema de negocio

En muchas organizaciones, RRHH trabaja con información distribuida entre:

- ERP / HRIS;
- módulos de payroll;
- sistemas de asistencia;
- contratos;
- vacaciones y permisos;
- documentos internos;
- políticas;
- procedimientos;
- archivos PDF/DOCX;
- hojas de cálculo;
- conocimiento operativo de personas específicas.

Esto genera:

- dependencia de usuarios técnicos;
- búsqueda manual de información;
- dificultad para relacionar datos de distintas áreas;
- riesgo de utilizar políticas desactualizadas;
- respuestas inconsistentes;
- tiempos altos para investigar incidencias;
- dificultad para justificar una recomendación con evidencia;
- limitada trazabilidad sobre cómo se llegó a una conclusión.

---

## 3. Oportunidad de negocio

PeopleOps AI puede convertirse en una capa de inteligencia sobre los sistemas existentes sin reemplazarlos.

La oportunidad consiste en permitir que RRHH:

- consulte información con lenguaje natural;
- combine hechos de distintas fuentes;
- consulte políticas vigentes;
- detecte inconsistencias;
- explique variaciones de payroll;
- identifique solicitudes que requieren revisión;
- reduzca dependencia de consultas técnicas;
- mantenga evidencia y trazabilidad;
- conserve control humano en decisiones sensibles.

---

## 4. Usuarios y stakeholders

### Usuarios principales
- Recursos Humanos;
- People Operations;
- Payroll;
- responsables de asistencia;
- responsables de contratos;
- responsables de vacaciones/permisos;
- jefaturas autorizadas;
- analistas HR.

### Stakeholders
- dirección;
- administración;
- TI;
- seguridad;
- responsables de ERP/HRIS;
- compliance/legal cuando corresponda.

---

## 5. Objetivos de negocio

1. Reducir el tiempo necesario para responder preguntas HR.
2. Disminuir la dependencia de conocimiento técnico del ERP/HRIS.
3. Facilitar análisis que combinen múltiples fuentes.
4. Mejorar el acceso a políticas y procedimientos vigentes.
5. Proporcionar evidencia para respuestas y recomendaciones.
6. Facilitar detección de inconsistencias entre asistencia y payroll.
7. Mantener revisión humana en situaciones sensibles.
8. Permitir que la solución se reutilice sobre distintos ERP/HRIS.
9. Evitar proyectos de integración invasivos sobre el sistema transaccional.
10. Crear una base extensible para nuevos casos de uso HR.

---

## 6. Capacidades de negocio esperadas

### Employee & Contract Intelligence
- consultas de empleados;
- estado contractual;
- vencimientos;
- documentación pendiente;
- relaciones con vacaciones/licencias.

### Attendance Intelligence
- tardanzas;
- ausencias;
- overtime;
- incidencias;
- análisis por empleado, área o período.

### Vacation & Leave Intelligence
- saldos;
- solicitudes;
- políticas aplicables;
- conflictos;
- necesidad de revisión humana.

### Payroll Intelligence
- explicación de cambios;
- comparación entre períodos;
- conceptos;
- descuentos;
- overtime pagado;
- reconciliación asistencia ↔ payroll;
- análisis agregado.

### Policy Intelligence
- búsqueda de políticas;
- versión vigente;
- evidencia;
- secciones;
- comparación entre versiones;
- detección de información insuficiente.

### Human Review
- identificación de situaciones sensibles;
- escalamiento;
- revisión;
- trazabilidad de decisión.

---

## 7. Preguntas de negocio representativas

- “¿Qué contratos vencen en los próximos 45 días?”
- “¿Qué empleados tienen más de 20 días de vacaciones pendientes?”
- “¿Puede este empleado solicitar 15 días de vacaciones en noviembre?”
- “¿Qué política regula esta solicitud?”
- “¿Por qué este empleado recibió menos neto este mes?”
- “¿Qué conceptos cambiaron respecto al período anterior?”
- “¿Qué empleados tienen horas extra registradas que no aparecen correctamente en nómina?”
- “¿Qué áreas presentan mayor ausentismo?”
- “¿Qué empleados tienen contrato próximo a vencer y vacaciones pendientes?”
- “¿Qué política estaba vigente en enero?”
- “¿Debe intervenir una persona antes de continuar?”

---

## 8. Resultados esperados

PeopleOps AI debe permitir:

- respuestas más rápidas;
- investigación cross-domain;
- mayor trazabilidad;
- menor dependencia de consultas manuales;
- mejor acceso a políticas;
- explicación de payroll;
- identificación de excepciones;
- evidencia reutilizable para revisión;
- integración progresiva con ERP/HRIS existentes.

---

## 9. Requisitos de negocio de integración

Los ERP/HRIS no comparten un esquema uniforme y pueden contener desarrollos específicos.

Por ello, la solución debe:

- evitar dependencia de tablas físicas específicas;
- descubrir lo que cada sistema conectado puede ofrecer;
- operar mediante una frontera de integración desacoplada;
- permitir que un adaptador/servidor especializado conozca el ERP real;
- mantener PeopleOps AI independiente del DBMS;
- permitir sustitución del sistema origen sin reescribir la lógica de negocio del copiloto.

MCP será la frontera de integración elegida para el MVP.

---

## 10. Requisitos de negocio sobre políticas

Las políticas y procedimientos forman parte del conocimiento propio de PeopleOps AI.

El producto debe permitir:

- cargar documentos;
- guardar metadata;
- manejar versiones;
- identificar vigencia;
- indexar;
- recuperar evidencia;
- abstenerse cuando no exista soporte suficiente.

Las políticas no dependen del MCP Server como fuente principal del MVP.

---

## 11. Requisitos de negocio sobre seguridad y privacidad

- datos del repositorio público serán sintéticos;
- acceso a payroll debe considerarse sensible;
- respuestas deben respetar autorización;
- información de otros empleados debe minimizarse;
- decisiones sensibles no deben automatizarse;
- debe existir audit trail;
- documentos deben tratarse como contenido no confiable;
- cualquier integración real debe utilizar mínimos privilegios.

---

## 12. Fuera de alcance de negocio

- reemplazar el ERP/HRIS;
- recruiting completo;
- performance management completo;
- despidos/promociones automáticos;
- sanciones automáticas;
- escritura automática de payroll;
- decisiones basadas en atributos sensibles;
- asesoría legal/laboral definitiva;
- implementación de adapters para todos los ERP existentes.

---

## 13. Criterios de éxito de negocio

El proyecto será exitoso si demuestra que:

1. un usuario HR puede formular preguntas no preprogramadas;
2. puede combinar datos y políticas;
3. puede explicar payroll con evidencia;
4. puede detectar inconsistencias;
5. puede escalar a revisión humana;
6. puede operar sin conocimiento técnico del esquema físico;
7. puede sustituir el origen de datos mediante MCP sin modificar la lógica principal;
8. responde en múltiples idiomas sin reglas lingüísticas hardcodeadas.

---

## 14. Relación con los demás documentos

Este BRD define **por qué existe el producto y qué resultados de negocio se esperan**.

La definición detallada del producto se encuentra en el PDD.

Los requisitos verificables se encuentran en el PRD.

Las decisiones técnicas y de arquitectura se documentarán posteriormente siguiendo el método AIDKIT.
