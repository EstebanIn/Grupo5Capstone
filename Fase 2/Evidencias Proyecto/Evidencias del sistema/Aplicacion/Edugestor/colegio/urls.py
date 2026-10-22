from django.urls import path
from . import views, views_ia

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path(
    "clientes/<slug:slug_colegio>/",
    views.landing_cliente,
    name="landing_cliente"
),
    
    # LOGIN
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    # PANELES
    path("panel/admin/", views.panel_admin, name="panel_admin"),
    path("panel/admin/", views.panel_admin, name="panel_admin"),
    path("panel/admin/usuarios/", views.panel_admin_usuarios, name="panel_admin_usuarios"),
    path("panel/admin/cursos/", views.panel_admin_cursos, name="panel_admin_cursos"),

    path("panel/admin/asignaturas/", views.panel_admin_asignaturas, name="panel_admin_asignaturas"),
    path("panel/admin/matriculas/", views.panel_admin_matriculas, name="panel_admin_matriculas"),
    path("panel/admin/reportes/", views.panel_admin_reportes, name="panel_admin_reportes"),
    path("panel/admin/perfil/", views.panel_admin_perfil, name="panel_admin_perfil"),
    path("panel/docente/", views.panel_docente, name="panel_docente"),
    path("panel/docente/cursos/", views.panel_docente_cursos, name="panel_docente_cursos"),
    path("panel/docente/notas/", views.panel_docente_notas, name="panel_docente_notas"),
    path("panel/docente/asistencia/", views.panel_docente_asistencia, name="panel_docente_asistencia"),
    path("panel/docente/alumnos/", views.panel_docente_alumnos, name="panel_docente_alumnos"),
    path("panel/docente/profesor-jefe/", views.panel_docente_jefatura, name="panel_docente_jefatura"),
    path("panel/docente/perfil/", views.panel_docente_perfil, name="panel_docente_perfil"),
    path("panel/alumno/", views.panel_alumno, name="panel_alumno"),
    path("panel/alumno/asignaturas/", views.panel_alumno_asignaturas, name="panel_alumno_asignaturas"),
    path("panel/alumno/notas/", views.panel_alumno_notas, name="panel_alumno_notas"),
    path("panel/alumno/asistencia/", views.panel_alumno_asistencia, name="panel_alumno_asistencia"),
    path("panel/alumno/perfil/", views.panel_alumno_perfil, name="panel_alumno_perfil"),
    path("panel/apoderado/", views.panel_apoderado, name="panel_apoderado"),
    path("panel/apoderado/estudiantes/",views.panel_apoderado_estudiantes,name="panel_apoderado_estudiantes"),
    path("panel/apoderado/notas/",views.panel_apoderado_notas,name="panel_apoderado_notas"),
    path("panel/apoderado/asistencia/",views.panel_apoderado_asistencia,name="panel_apoderado_asistencia"),
    path("panel/apoderado/pagos/",views.panel_apoderado_pagos,name="panel_apoderado_pagos"),
    path("panel/apoderado/perfil/",views.panel_apoderado_perfil,name="panel_apoderado_perfil"),
    path('panel-admin/usuarios/bloquear/<int:usuario_id>/', views.bloquear_usuario, name='bloquear_usuario'),
    path('panel-admin/usuarios/eliminar/<int:usuario_id>/', views.eliminar_usuario, name='eliminar_usuario'),
    path('admin-dashboard/', views.panel_admin, name='panel_admin'),
    path('admin-dashboard/usuarios/', views.panel_admin_usuarios, name='panel_admin_usuarios'),

    # Asistentes de IA
    path("panel/docente/asistente/", views_ia.asistente_docente, name="asistente_docente"),
    path("panel/docente/asistente/prueba/", views_ia.ia_crear_prueba, name="ia_crear_prueba"),
    path("panel/docente/asistente/rubrica/", views_ia.ia_crear_rubrica, name="ia_crear_rubrica"),
    path("panel/docente/asistente/material/", views_ia.ia_crear_material, name="ia_crear_material"),
    path("panel/docente/asistente/revisar/", views_ia.ia_revisar_prueba, name="ia_revisar_prueba"),
    path("panel/docente/asistente/<int:pk>/", views_ia.ia_instrumento, name="ia_instrumento"),
    path("panel/docente/asistente/<int:pk>/eliminar/", views_ia.ia_eliminar_instrumento, name="ia_eliminar_instrumento"),
    path("panel/docente/asistente/corregir/", views_ia.ia_corregir, name="ia_corregir"),
    path("panel/docente/asistente/<int:pk>/corregir/", views_ia.ia_corregir_prueba, name="ia_corregir_prueba"),
    path("panel/docente/asistente/correccion/<int:pk>/", views_ia.ia_correccion, name="ia_correccion"),
    path("panel/alumno/tutor/", views_ia.tutor_alumno, name="tutor_alumno"),

    # Notas docente
    path("panel/docente/notas/crear-evaluacion/", views.crear_evaluacion, name="crear_evaluacion"),
    path("panel/docente/notas/ingresar/<int:evaluacion_id>/", views.ingresar_notas, name="ingresar_notas"),
    path("panel/docente/notas/editar/<int:evaluacion_id>/", views.editar_evaluacion, name="editar_evaluacion"),
    path("panel/docente/notas/eliminar/<int:evaluacion_id>/", views.eliminar_evaluacion, name="eliminar_evaluacion"),

    # FORMULARIOS
    path("alumnos/crear/", views.crear_alumno_view, name="crear_alumno"),
    path("docentes/crear/", views.crear_docente, name="crear_docente"),
    path("apoderados/crear/", views.crear_apoderado_view, name="crear_apoderado"),

    # MATRÍCULA
    path(
        "matriculas/crear/",
        views.crear_matricula_view,
        name="crear_matricula"
    ),

    # Matrículas CRUD
    path('admin-dashboard/matriculas/nueva/', views.crear_matricula_admin, name='crear_matricula_admin'),
    path('admin-dashboard/matriculas/editar/<int:pk>/', views.editar_matricula_admin, name='editar_matricula_admin'),
    path('admin-dashboard/matriculas/eliminar/<int:pk>/', views.eliminar_matricula_admin, name='eliminar_matricula_admin'),
    path("panel-admin/matriculas/alumno/<int:alumno_id>/cancelar/",views.cancelar_matriculacion_admin, name="cancelar_matriculacion_admin"
),

    # Cursos CRUD
    path('panel/cursos/', views.panel_admin_cursos, name='panel_admin_cursos'),
    path('admin-dashboard/cursos/', views.panel_admin_cursos, name='panel_admin_cursos'),
    path('admin-dashboard/cursos/nuevo/', views.crear_curso, name='crear_curso'),
    path('admin-dashboard/cursos/editar/<int:pk>/', views.editar_curso, name='editar_curso'),
    path('admin-dashboard/cursos/eliminar/<int:pk>/', views.eliminar_curso, name='eliminar_curso'),
    path('admin-dashboard/cursos/carga-masiva/', views.carga_masiva_cursos, name='carga_masiva_cursos'),
    
    
    
    path('admin-dashboard/asignaturas/', views.panel_admin_asignaturas, name='panel_admin_asignaturas'),
    path('admin-dashboard/matriculas/', views.panel_admin_matriculas, name='panel_admin_matriculas'),
    path('admin-dashboard/reportes/', views.panel_admin_reportes, name='panel_admin_reportes'),
    path('admin-dashboard/perfil/', views.panel_admin_perfil, name='panel_admin_perfil'),

    # Rutas para Asignaturas
    path('panel/asignaturas/crear/', views.crear_asignatura, name='crear_asignatura'),
    path('panel/asignaturas/editar/<int:id>/', views.editar_asignatura, name='editar_asignatura'),
    path('panel/asignaturas/eliminar/<int:id>/', views.eliminar_asignatura, name='eliminar_asignatura'),
    path('panel/asignaturas/carga-masiva/', views.carga_masiva_asignaturas, name='carga_masiva_asignaturas'),

    path('panel/docentes/', views.panel_admin_docentes, name='panel_admin_docentes'),
    path('panel/docentes/nuevo/', views.crear_docente, name='crear_docente'),
    path('panel/docentes/editar/<int:pk>/', views.editar_docente, name='editar_docente'),
    path('panel/docentes/eliminar/<int:pk>/', views.eliminar_docente, name='eliminar_docente'),

    # rEGISTRO ALUMNO
 # REGISTRO ALUMNO / POSTULACIONES

path(
    "postulacion-alumno/",
    views.postulacion_alumno,
    name="postulacion_alumno"
),

path(
    "clientes/<slug:slug_colegio>/postulacion/",
    views.postulacion_alumno,
    name="postulacion_alumno_cliente"
),

path(
    "clientes/<slug:slug_colegio>/postulacion-exitosa/",
    views.postulacion_exitosa,
    name="postulacion_exitosa"
),

path(
    "panel-admin/registrar-alumno/",
    views.registrar_alumno,
    name="registrar_alumno"
),

# API Autocomplete
path("api/buscar-apoderados/", views.api_buscar_apoderados, name="api_buscar_apoderados"),
path("api/buscar-docentes/", views.api_buscar_docentes, name="api_buscar_docentes"),

path(
    "panel-admin/postulaciones/",
    views.panel_admin_postulaciones,
    name="panel_admin_postulaciones"
),

path(
    "panel-admin/postulaciones/<int:pk>/aprobar/",
    views.aprobar_postulacion,
    name="aprobar_postulacion"
),

path(
    "panel-admin/postulaciones/<int:pk>/rechazar/",
    views.rechazar_postulacion,
    name="rechazar_postulacion"
),
]
