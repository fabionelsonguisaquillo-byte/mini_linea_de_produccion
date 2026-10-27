
def clasificar_hsv(h, s, v):
    """
    Clasificador simplificado para pruebas.

    Entrada:
        h: tono HSV (0-179)
        s: saturación (0-255)
        v: brillo (0-255)

    Salida:
        "ROJA", "AZUL" o "MALA"
    """

    # Validar que los valores estén dentro de los rangos HSV
    if not (0 <= h <= 179 and 0 <= s <= 255 and 0 <= v <= 255):
        raise ValueError("Valores HSV fuera de rango")

    # Rechazar colores con poca saturación o brillo
    if s < 35 or v < 35:
        return "MALA"

    # Regla para rojo
    if h <= 18 or h >= 165:
        return "ROJA"

    # Regla para azul
    if 85 <= h <= 140:
        return "AZUL"

    # Si no coincide con las reglas
    return "MALA"


# Caso 1: dentro de los parámetros
print("Caso 1:", clasificar_hsv(10, 180, 180))

# Caso 2: justo en el límite rojo
print("Caso 2:", clasificar_hsv(18, 180, 180))

# Caso 3: fuera de los rangos de color aceptados
print("Caso 3:", clasificar_hsv(40, 180, 180))
