# 0001 — Migración a PostgreSQL y datos sintéticos reproducibles

- **Estado:** aceptada
- **Fecha:** 2026-09-21
- **Objetivo específico:** 2 (Guía 1, Definición Proyecto APT)

## Contexto

El sistema usa SQLite. El rediseño multi-institución agrega restricciones de
unicidad compuestas y más adelante filtros por institución en todas las
consultas; esas restricciones deben comportarse como en producción. Además, el
proyecto trata datos de menores y los niveles gratuitos de las APIs de IA pueden
usar el contenido enviado, por lo que no puede entrar ningún dato real.

## Alternativas evaluadas

| Alternativa | Ventaja | Desventaja |
|---|---|---|
| Seguir con SQLite hasta el final | Cero cambios | Las restricciones y tipos difieren de producción; habría que depurar dos veces |
| PostgreSQL instalado en cada equipo | Sin Docker | Versiones distintas por integrante, instalación manual |
| **PostgreSQL 17 en Docker (elegida)** | Misma versión para todos, un comando | Requiere Docker Desktop |

Para los datos de prueba: exportar la base de alguien (no reproducible, puede
tener datos reales) vs. **comando con semilla fija (elegida)**.

## Decisión

- `settings.py` lee la configuración desde variables de entorno (`.env`). Con
  `POSTGRES_DB` definido usa PostgreSQL; sin él, SQLite. Así el cambio no rompe
  el entorno de quien aún no lo adopta.
- `docker-compose.yml` levanta PostgreSQL 17 local.
- `manage.py generar_datos_sinteticos` genera una escuela rural completa con
  semilla fija. RUT válidos pero generados, correos bajo el dominio reservado
  `.test`.
- La migración de motor va **antes** del cambio de esquema multi-institución.

## Verificación

- Las 15 migraciones existentes aplican sin cambios sobre PostgreSQL.
- La suite completa (26 pruebas) pasa en PostgreSQL y en SQLite.
- Pruebas nuevas: coherencia de datos y RUT válidos, reproducibilidad con la
  misma semilla, y que el comando no sobrescriba datos sin `--limpiar`.
- Los 23 paneles de los cuatro roles responden correctamente con los datos generados.
