# 0002 — Modelo de datos multi-institución

- **Estado:** aceptada
- **Fecha:** 2026-09-21
- **Objetivo específico:** 1 (Guía 1, Definición Proyecto APT)

## Contexto

EduGestor atendía a un solo establecimiento. El objetivo es que varias escuelas
compartan la plataforma sin compartir sus datos, y que una misma persona (un
apoderado con hijos en dos escuelas, un docente que hace clases en ambas) pueda
existir legítimamente en más de una. Varias restricciones de unicidad eran
globales (RUT, correo del docente, correo del apoderado, año/semestre del
período) y lo impedían.

## Alternativas evaluadas

| Estrategia | Aislamiento | Costo / complejidad | Decisión |
|---|---|---|---|
| Una base de datos por institución | Máximo | Una conexión y migración por escuela; inviable para escuelas pequeñas | Descartada |
| Un esquema PostgreSQL por institución (django-tenants) | Alto | Dependencia externa, migraciones por esquema, más difícil de probar localmente | Descartada |
| **Esquema compartido con columna `institucion` (multi-inquilino lógico)** | Lógico, verificable con pruebas | Un solo esquema y una sola migración; el aislamiento depende del código | **Elegida** |

Para aplicar el filtro se evaluó: (a) agregar `.filter(institucion=...)` a mano en
cada consulta de las ~2.700 líneas de vistas, frágil porque basta olvidar uno; y
(b) **un manager por defecto que filtra por la institución activa del request
(elegida)**, que aísla las vistas existentes sin reescribirlas.

## Decisión

- Nueva entidad `Institucion` (nombre, slug, activa).
- Los 14 modelos declaran `institucion` mediante la base abstracta
  `ModeloInstitucional`. `Usuario` la tiene opcional solo para superusuarios
  de plataforma sin rol.
- **Herencia de la institución:** cada modelo declara sus FK padre
  (`PADRES_INSTITUCION`). Al guardar, la institución se toma del padre (una
  Nota la toma de su Evaluación); si no hay padre, de la institución activa.
  Si dos padres pertenecen a instituciones distintas, se lanza
  `InstitucionCruzadaError`. Lo mismo vale para las relaciones N:N
  (`Asignatura.docentes`, `Matricula.apoderados`).
- **Institución activa:** `InstitucionMiddleware` la resuelve desde el usuario
  autenticado o, en páginas públicas, desde el `slug_colegio` de la URL. Las
  rutas con slug (landing, postulación) son públicas: se atienden con la
  institución de la URL aunque quien visita tenga sesión en otra, porque no
  muestran datos privados. *(Primera versión: respondían 404 a un usuario de
  otra institución; se corrigió porque bloqueaba páginas públicas.)*
- **Filtro por defecto:** `InstitucionQuerySet` agrega el filtro al *crear o
  clonar* el queryset, nunca modificando el original. Así, los querysets
  definidos al importar un formulario (`ModelChoiceField`) se filtran en cada
  request y no quedan fijados a la institución del primer request.
- **Unicidades compuestas:** `(institucion, rut)`, `(institucion,
  email_institucional)`, `(institucion, email)` y `(institucion, anio,
  semestre)`. Las demás (nota por evaluación y alumno, asistencia por fecha,
  etc.) ya quedan acotadas porque sus FK pertenecen a una sola institución.
- **Migración en tres pasos:**
  1. `0016`: crea `Institucion` y agrega `institucion` como campo opcional.
  2. `0017`: asigna los datos existentes a "Instituto Chimbarongo" (la base
     previa era de un solo establecimiento).
  3. `0018`: vuelve obligatorio el campo y reemplaza las unicidades globales
     por compuestas.

## Verificación

- 38 pruebas pasan en PostgreSQL y en SQLite. Las nuevas de aislamiento
  verifican: que todos los modelos declaren su institución, que cada modelo
  filtre por la institución activa, que un queryset definido al importar se
  filtre al usarse, que un admin no vea ni edite cursos o usuarios de otra
  institución, que no se puedan mezclar instituciones (FK y N:N), que la misma
  persona pueda estar en dos instituciones y que el RUT no se repita dentro de
  una.
- La migración se aplicó sobre una base con datos (4.685 registros): ningún
  registro quedó sin institución. También se probó revertirla (`migrate
  colegio 0015`) y volver a aplicarla.
- Prueba de humo: 4 roles × 3 instituciones, 72 páginas; todas responden 200 y
  ninguna contiene usuarios de otra institución.

## Consecuencias y pendientes

- **El username sigue siendo único en toda la plataforma** (y deriva del
  RUT). Por eso los formularios rechazan un RUT que ya tiene cuenta en otra
  institución. Resolverlo es parte del siguiente incremento (autenticación por
  institución, ingreso por la dirección propia de cada establecimiento). En
  los datos sintéticos, la docente compartida usa usernames distintos
  (`chimbarongo.docente1`, `maitenes.docente1`).
- **Sin institución activa no se filtra** (comandos de gestión, migraciones,
  superusuario de plataforma). El incremento de autenticación debe decidir si
  un request sin institución debe fallar de forma cerrada.
- `bulk_create()` y `QuerySet.update()` no pasan por `save()`: quien los use
  debe asignar `institucion` explícitamente (así lo hace el comando de datos).
- En el admin de Django, `institucion` no es editable en los modelos
  institucionales: para crear registros ahí se necesita un superusuario
  asociado a una institución.
- La landing pública sigue teniendo el contenido de Chimbarongo fijo; solo el
  enlace de postulación usa la institución del slug.
