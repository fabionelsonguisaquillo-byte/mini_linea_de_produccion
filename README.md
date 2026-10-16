# MVP — Mini línea de producción automatizada

## 1. Descripción del proyecto

Este proyecto consiste en desarrollar un MVP de una mini línea de producción automatizada capaz de detectar piezas y clasificarlas según su color mediante visión artificial.

El sistema utiliza Python y OpenCV para analizar las imágenes capturadas por una cámara y un dashboard para visualizar los resultados de la clasificación.

## 2. Objetivo

Desarrollar una demostración funcional que permita detectar y clasificar piezas rojas, azules y de otros colores, registrar los resultados y mostrar los contadores de producción.

## 3. Alcance del MVP

El proyecto contempla:

* Una banda transportadora para desplazar las piezas.
* Un sensor de presencia para detectar la llegada de las piezas.
* Una cámara para capturar imágenes.
* Python y OpenCV para detectar y clasificar los colores.
* Un servomotor para separar las piezas según su clasificación.
* Un dashboard para mostrar el estado del sistema y los contadores.

La integración y validación física de estos componentes debe comprobarse mediante pruebas del prototipo.

## 4. Clasificación de las piezas

* **ROJA:** pieza que coincide con el color rojo de referencia.
* **AZUL:** pieza que coincide con el color azul de referencia.
* **MALA:** pieza que no coincide con ninguno de los colores establecidos.

El sistema debe actualizar el contador correspondiente al registrar cada pieza.

## 5. Tecnologías utilizadas

* Python.
* OpenCV para el procesamiento de imágenes.
* Tkinter para la interfaz gráfica.
* NumPy para operaciones numéricas.
* Git y GitHub para el control de versiones y la documentación del proyecto.

## 6. Funcionamiento esperado

1. Iniciar el sistema desde el dashboard.
2. Detectar la presencia de una pieza frente a la cámara.
3. Analizar su color.
4. Clasificarla como roja, azul o mala.
5. Actualizar los contadores de producción.
6. Registrar el resultado en un archivo CSV.
7. Detener el procesamiento cuando se pulse el botón DETENER.

## 7. Pruebas y validación

Se deben realizar pruebas con piezas rojas, azules y de otros colores, además de verificar el comportamiento del sistema cuando no hay piezas y cuando está detenido.

Los resultados de las pruebas físicas deben registrarse en la documentación del proyecto. No se considerará validada una función hasta comprobar su funcionamiento en el prototipo.

## 8. Estado del proyecto

El proyecto se encuentra en desarrollo. Se están revisando y probando los procesos de detección, clasificación, conteo y control del estado del dashboard.

La integración con el sensor de presencia, la banda transportadora y el servomotor debe verificarse según el avance real del prototipo.
