import re
from django.core.exceptions import ValidationError


def limpiar_rut(rut):
    return rut.replace(".", "").replace("-", "").upper()


def validar_rut_chileno(rut):
    if not rut:
        raise ValidationError("El RUT es obligatorio.")

    rut = rut.strip().upper()

    patron = r"^\d{1,2}\.\d{3}\.\d{3}-[\dKk]$"
    if not re.match(patron, rut):
        raise ValidationError("El RUT debe tener el formato 12.345.678-9.")

    rut_limpio = limpiar_rut(rut)

    cuerpo = rut_limpio[:-1]
    dv = rut_limpio[-1]

    if not cuerpo.isdigit():
        raise ValidationError("El cuerpo del RUT debe contener solo números.")

    suma = 0
    multiplicador = 2

    for numero in reversed(cuerpo):
        suma += int(numero) * multiplicador
        multiplicador += 1

        if multiplicador > 7:
            multiplicador = 2

    resto = suma % 11
    dv_calculado = 11 - resto

    if dv_calculado == 11:
        dv_calculado = "0"
    elif dv_calculado == 10:
        dv_calculado = "K"
    else:
        dv_calculado = str(dv_calculado)

    if dv != dv_calculado:
        raise ValidationError("El RUT ingresado no es válido.")