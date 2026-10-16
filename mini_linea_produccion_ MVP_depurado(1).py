
import cv2
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk
import csv
import os
from datetime import datetime

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

CAMERA_INDEX = 0

FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Área mínima para considerar que existe una pieza
MIN_OBJECT_AREA = 5000

# Umbral de saturación para la detección inicial de objetos
MIN_SATURATION = 50

# Tiempo mínimo entre clasificaciones
CLASSIFICATION_DELAY = 1.5

# ============================================================
# COLORES DE REFERENCIA EN HSV
# ============================================================
#
# OpenCV utiliza:
# H = 0 - 179
# S = 0 - 255
# V = 0 - 255
#
# Estos valores son INICIALES.
# Deben calibrarse con las piezas reales.
#
# Rojo de referencia
RED_REFERENCE = np.array([0, 200, 200])

# Azul de referencia
BLUE_REFERENCE = np.array([110, 200, 200])

# Tolerancias
# H = tolerancia de tono
# S = tolerancia de saturación
# V = tolerancia de brillo
RED_TOLERANCE = np.array([10, 70, 70])
BLUE_TOLERANCE = np.array([10, 70, 70])

# ============================================================
# COMUNICACIÓN CON ESP32
# ============================================================

ESP32_ENABLED = False

ESP32_PORT = "COM3"
ESP32_BAUDRATE = 115200

try:
    import serial
except ImportError:
    serial = None


# ============================================================
# SISTEMA PRINCIPAL
# ============================================================

class ProductionSystem:

    def __init__(self, root):

        self.root = root
        self.root.title("Mini Línea de Producción")
        self.root.geometry("1000x700")

        # ----------------------------------------------------
        # ESTADO DEL SISTEMA
        # ----------------------------------------------------

        self.system_running = False

        self.total_pieces = 0
        self.red_pieces = 0
        self.blue_pieces = 0
        self.bad_pieces = 0

        self.last_result = "SIN CLASIFICAR"

        self.processing_piece = False
        self.no_piece_frames = 0
        self.NO_PIECE_RESET_FRAMES = 15
        self.last_classification_time = 0
        self.closing = False

        self.serial_connection = None

        # ----------------------------------------------------
        # CÁMARA
        # ----------------------------------------------------

        self.camera = cv2.VideoCapture(CAMERA_INDEX)

        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

        if not self.camera.isOpened():
            print("ERROR: No se pudo abrir la cámara.")
            self.camera.release()
            self.camera = None

        # ----------------------------------------------------
        # CSV
        # ----------------------------------------------------

        self.csv_file = "registro_produccion.csv"

        self.create_csv()

        # ----------------------------------------------------
        # INTERFAZ
        # ----------------------------------------------------

        self.create_interface()

        # ----------------------------------------------------
        # ESP32
        # ----------------------------------------------------

        self.connect_esp32()

        # ----------------------------------------------------
        # INICIAR VIDEO
        # ----------------------------------------------------

        self.update_camera()

        # Cerrar correctamente
        self.root.protocol("WM_DELETE_WINDOW", self.close_system)

    # ========================================================
    # CREAR CSV
    # ========================================================

    def create_csv(self):

        if not os.path.exists(self.csv_file):

            with open(
                self.csv_file,
                mode="w",
                newline="",
                encoding="utf-8"
            ) as file:

                writer = csv.writer(file)

                writer.writerow([
                    "Fecha",
                    "Hora",
                    "Color detectado",
                    "Resultado"
                ])

    # ========================================================
    # INTERFAZ
    # ========================================================

    def create_interface(self):

        # ----------------------------------------------------
        # TÍTULO
        # ----------------------------------------------------

        title = tk.Label(
            self.root,
            text="MINI LÍNEA DE PRODUCCIÓN",
            font=("Arial", 22, "bold")
        )

        title.pack(pady=10)

        # ----------------------------------------------------
        # FRAME PRINCIPAL
        # ----------------------------------------------------

        main_frame = tk.Frame(self.root)

        main_frame.pack(fill="both", expand=True)

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        self.video_label = tk.Label(main_frame)

        self.video_label.pack(
            side="left",
            padx=20,
            pady=20
        )

        # ----------------------------------------------------
        # PANEL DE INFORMACIÓN
        # ----------------------------------------------------

        info_frame = tk.Frame(main_frame)

        info_frame.pack(
            side="right",
            fill="y",
            padx=20,
            pady=20
        )

        # Estado

        tk.Label(
            info_frame,
            text="Estado del sistema",
            font=("Arial", 14, "bold")
        ).pack(pady=5)

        self.status_label = tk.Label(
            info_frame,
            text="DETENIDO",
            font=("Arial", 16)
        )

        self.status_label.pack(pady=5)

        # Sensor

        tk.Label(
            info_frame,
            text="Sensor / Pieza",
            font=("Arial", 14, "bold")
        ).pack(pady=5)

        self.sensor_label = tk.Label(
            info_frame,
            text="SIN PIEZA",
            font=("Arial", 14)
        )

        self.sensor_label.pack(pady=5)

        # Color

        tk.Label(
            info_frame,
            text="Color detectado",
            font=("Arial", 14, "bold")
        ).pack(pady=5)

        self.color_label = tk.Label(
            info_frame,
            text="---",
            font=("Arial", 16)
        )

        self.color_label.pack(pady=5)

        # Resultado

        tk.Label(
            info_frame,
            text="Último resultado",
            font=("Arial", 14, "bold")
        ).pack(pady=5)

        self.result_label = tk.Label(
            info_frame,
            text="SIN CLASIFICAR",
            font=("Arial", 16, "bold")
        )

        self.result_label.pack(pady=5)

        # ----------------------------------------------------
        # CONTADORES
        # ----------------------------------------------------

        tk.Label(
            info_frame,
            text="CONTADORES",
            font=("Arial", 14, "bold")
        ).pack(pady=(20, 5))

        self.total_label = tk.Label(
            info_frame,
            text="Total: 0",
            font=("Arial", 12)
        )

        self.total_label.pack()

        self.red_label = tk.Label(
            info_frame,
            text="Rojas: 0",
            font=("Arial", 12)
        )

        self.red_label.pack()

        self.blue_label = tk.Label(
            info_frame,
            text="Azules: 0",
            font=("Arial", 12)
        )

        self.blue_label.pack()

        self.bad_label = tk.Label(
            info_frame,
            text="Malas: 0",
            font=("Arial", 12)
        )

        self.bad_label.pack()

        # ----------------------------------------------------
        # BOTONES
        # ----------------------------------------------------

        button_frame = tk.Frame(self.root)

        button_frame.pack(pady=10)

        self.start_button = tk.Button(
            button_frame,
            text="INICIAR",
            font=("Arial", 12, "bold"),
            command=self.start_system,
            width=12
        )

        self.start_button.grid(
            row=0,
            column=0,
            padx=10
        )

        self.stop_button = tk.Button(
            button_frame,
            text="DETENER",
            font=("Arial", 12, "bold"),
            command=self.stop_system,
            width=12
        )

        self.stop_button.grid(
            row=0,
            column=1,
            padx=10
        )

    # ========================================================
    # CONEXIÓN ESP32
    # ========================================================

    def connect_esp32(self):

        if not ESP32_ENABLED:
            print("ESP32: modo simulación.")

            return

        if serial is None:

            print(
                "ERROR: PySerial no está instalado."
            )

            return

        try:

            self.serial_connection = serial.Serial(
                ESP32_PORT,
                ESP32_BAUDRATE,
                timeout=1
            )

            print("ESP32 conectado.")

        except Exception as error:

            print(
                "No se pudo conectar al ESP32:",
                error
            )

    # ========================================================
    # ENVIAR RESULTADO AL ESP32
    # ========================================================

    def send_to_esp32(self, result):

        print(
            "Resultado enviado al ESP32:",
            result
        )

        if (
            ESP32_ENABLED
            and self.serial_connection is not None
        ):

            try:

                message = result + "\n"

                self.serial_connection.write(
                    message.encode()
                )

            except Exception as error:

                print(
                    "Error enviando al ESP32:",
                    error
                )

    # ========================================================
    # INICIAR SISTEMA
    # ========================================================

    def start_system(self):

        self.system_running = True

        self.status_label.config(
            text="FUNCIONANDO"
        )

    # ========================================================
    # DETENER SISTEMA
    # ========================================================

    def stop_system(self):

        self.system_running = False

        self.status_label.config(
            text="DETENIDO"
        )

        self.sensor_label.config(
            text="SIN PIEZA"
        )

    # ========================================================
    # ACTUALIZAR CÁMARA
    # ========================================================

    def update_camera(self):
        # No programar nuevos ciclos al cerrar la ventana.
        if self.closing:
            return

        if self.camera is None:
            self.status_label.config(text="ERROR DE CÁMARA")
            return

        ret, frame = self.camera.read()

        if not ret or frame is None:
            self.status_label.config(text="ERROR DE LECTURA")
            self.root.after(100, self.update_camera)
            return

        if self.system_running:
            self.status_label.config(text="FUNCIONANDO")
        else:
            self.status_label.config(text="DETENIDO")

        processed_frame = self.process_frame(frame)

        # Convertir BGR a RGB.
        rgb_frame = cv2.cvtColor(
            processed_frame,
            cv2.COLOR_BGR2RGB
        )

        image = Image.fromarray(rgb_frame)
        image = image.resize((640, 480))
        photo = ImageTk.PhotoImage(image=image)

        self.video_label.configure(image=photo)
        self.video_label.image = photo

        self.root.after(30, self.update_camera)

    # ========================================================
    # PROCESAR IMAGEN
    # ========================================================

    def start_system(self):
    if self.camera is None or not self.camera.isOpened():
        self.status_label.config(text="ERROR DE CÁMARA")
        return

    self.system_running = True
    self.processing_piece = False
    self.no_piece_frames = 0

    self.status_label.config(text="FUNCIONANDO")
    self.sensor_label.config(text="SIN PIEZA")
    self.color_label.config(text="---")
    self.result_label.config(text="SIN CLASIFICAR")

    print("Sistema iniciado correctamente.")


def stop_system(self):
    self.system_running = False

    # Reiniciar el estado de detección.
    self.processing_piece = False
    self.no_piece_frames = 0

    self.status_label.config(text="DETENIDO")
    self.sensor_label.config(text="SIN PIEZA")
    self.color_label.config(text="---")
    self.result_label.config(text="SIN CLASIFICAR")

    print("Sistema detenido. Conteo desactivado."
         )

        # ----------------------------------------------------
        # DETECCIÓN GENERAL DE LA PIEZA
        # ----------------------------------------------------

        saturation = hsv[:, :, 1]

        _, object_mask = cv2.threshold(
            saturation,
            MIN_SATURATION,
            255,
            cv2.THRESH_BINARY
        )

        # Limpiar ruido

        kernel = np.ones(
            (5, 5),
            np.uint8
        )

        object_mask = cv2.morphologyEx(
            object_mask,
            cv2.MORPH_OPEN,
            kernel
        )

        object_mask = cv2.morphologyEx(
            object_mask,
            cv2.MORPH_CLOSE,
            kernel
        )

        contours, _ = cv2.findContours(
            object_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        # ----------------------------------------------------
        # BUSCAR LA PIEZA MÁS GRANDE
        # ----------------------------------------------------

        largest_contour = None
        largest_area = 0

        for contour in contours:

            area = cv2.contourArea(
                contour
            )

            if area > largest_area:

                largest_area = area

                largest_contour = contour

        # ----------------------------------------------------
        # NO HAY PIEZA
        # ----------------------------------------------------

        if (
            largest_contour is None
            or largest_area < MIN_OBJECT_AREA
        ):

            self.sensor_label.config(
                text="SIN PIEZA"
            )

            # Evitar liberar el bloqueo por una pérdida momentánea
            # de detección causada por ruido o vibración.
            self.no_piece_frames += 1
            if self.no_piece_frames >= self.NO_PIECE_RESET_FRAMES:
                self.processing_piece = False

            return display_frame

        # ----------------------------------------------------
        # HAY PIEZA
        # ----------------------------------------------------

        self.no_piece_frames = 0

        self.sensor_label.config(
            text="PIEZA DETECTADA"
        )

        x, y, w, h = cv2.boundingRect(
            largest_contour
        )

        cv2.rectangle(
            display_frame,
            (x, y),
            (x + w, y + h),
            (255, 255, 255),
            2
        )

        # ----------------------------------------------------
        # EXTRAER ROI
        # ----------------------------------------------------

        roi = hsv[y:y+h, x:x+w]

        if roi.size == 0:
            return display_frame

        # Crear una máscara local para medir solo los píxeles
        # interiores del contorno, excluyendo el fondo del rectángulo.
        contour_mask = np.zeros((h, w), dtype=np.uint8)
        local_contour = largest_contour.copy()
        local_contour[:, 0, 0] -= x
        local_contour[:, 0, 1] -= y

        cv2.drawContours(
            contour_mask,
            [local_contour],
            -1,
            255,
            thickness=cv2.FILLED
        )

        pixels = roi[contour_mask > 0]
        if pixels.size == 0:
            return display_frame

        # ----------------------------------------------------
        # CLASIFICAR COLOR
        # ----------------------------------------------------

        color, result = self.classify_color(pixels)

        # Mostrar resultado en pantalla

        self.color_label.config(
            text=color
        )

        # ----------------------------------------------------
        # CLASIFICAR UNA SOLA VEZ
        # ----------------------------------------------------

        current_time = datetime.now().timestamp()

        if (
            self.system_running
            and not self.processing_piece
            and (
                current_time
                - self.last_classification_time
                >= CLASSIFICATION_DELAY
            )
        ):

            self.processing_piece = True

            self.last_classification_time = current_time

            self.register_result(
                color,
                result
            )

            self.send_to_esp32(
                result
            )

            self.show_result(
                result
            )

        return display_frame

    # ========================================================
    # CLASIFICACIÓN DEL COLOR
    # ========================================================

    def classify_color(self, pixels):
        """
        Clasifica un conjunto de píxeles HSV (N x 3), no una imagen
        rectangular. La mediana reduce la influencia de píxeles atípicos.
        """
        pixels = np.asarray(pixels)
        if pixels.size == 0:
            return "OTRO", "MALA"

        pixels = pixels.reshape(-1, 3).astype(np.float32)

        # Hue es circular en HSV: 179 y 0 son tonos cercanos.
        # Usar media circular evita que los rojos cercanos al límite
        # se interpreten erróneamente como cian/verde.
        hue_angles = pixels[:, 0] * (2.0 * np.pi / 180.0)
        mean_sin = np.mean(np.sin(hue_angles))
        mean_cos = np.mean(np.cos(hue_angles))
        hue = (np.arctan2(mean_sin, mean_cos) % (2.0 * np.pi))
        hue = hue * (180.0 / (2.0 * np.pi))

        hsv_color = np.array([
            hue,
            np.median(pixels[:, 1]),
            np.median(pixels[:, 2])
        ], dtype=np.float32)

        # ----------------------------------------------------
        # REFERENCIAS
        # ----------------------------------------------------

        red_distance = self.color_distance(
            hsv_color,
            RED_REFERENCE
        )

        blue_distance = self.color_distance(
            hsv_color,
            BLUE_REFERENCE
        )

        # ----------------------------------------------------
        # COMPARAR TOLERANCIAS
        # ----------------------------------------------------

        red_valid = self.color_matches_reference(
            hsv_color, RED_REFERENCE, RED_TOLERANCE
        )

        blue_valid = self.color_matches_reference(
            hsv_color, BLUE_REFERENCE, BLUE_TOLERANCE
        )

        # ----------------------------------------------------
        # DECISIÓN
        # ----------------------------------------------------

        if red_valid and (
            red_distance < blue_distance
        ):

            return "ROJO", "ROJA"

        elif blue_valid:

            return "AZUL", "AZUL"

        else:

            return "OTRO", "MALA"

    def color_matches_reference(self, color, reference, tolerance):
        """Comprueba tolerancias por canal, con tono HSV circular."""
        hue_difference = abs(float(color[0]) - float(reference[0]))
        hue_difference = min(hue_difference, 180.0 - hue_difference)

        saturation_difference = abs(float(color[1]) - float(reference[1]))
        value_difference = abs(float(color[2]) - float(reference[2]))

        return (
            hue_difference <= float(tolerance[0])
            and saturation_difference <= float(tolerance[1])
            and value_difference <= float(tolerance[2])
        )

    # ========================================================
    # DISTANCIA ENTRE COLORES
    # ========================================================

    def color_distance(
        self,
        color,
        reference
    ):

        difference = (
            color.astype(np.float32)
            - reference.astype(np.float32)
        )

        # Diferencia de Hue

        hue_difference = abs(
            difference[0]
        )

        # El Hue es circular en HSV.
        # 0 y 179 están cerca.
        hue_difference = min(
            hue_difference,
            180 - hue_difference
        )

        saturation_difference = abs(
            difference[1]
        )

        value_difference = abs(
            difference[2]
        )

        # Distancia ponderada

        distance = np.sqrt(
            (
                hue_difference ** 2
            )
            + (
                saturation_difference ** 2
            )
            + (
                value_difference ** 2
            )
        )

        return distance

    # ========================================================
    # CALCULAR DISTANCIA DE TOLERANCIA
    # ========================================================

    def tolerance_distance(
        self,
        tolerance
    ):

        return np.sqrt(
            tolerance[0] ** 2
            + tolerance[1] ** 2
            + tolerance[2] ** 2
        )

    # ========================================================
    # MOSTRAR RESULTADO
    # ========================================================

    def show_result(self, result):

        self.result_label.config(
            text=result
        )

    # ========================================================
    # REGISTRAR RESULTADO
    # ========================================================

    def register_result(
        self,
        color,
        result
    ):

        now = datetime.now()

        date = now.strftime(
            "%Y-%m-%d"
        )

        time = now.strftime(
            "%H:%M:%S"
        )

        # Contadores

        self.total_pieces += 1

        if result == "ROJA":

            self.red_pieces += 1

        elif result == "AZUL":

            self.blue_pieces += 1

        else:

            self.bad_pieces += 1

        # Actualizar dashboard

        self.total_label.config(
            text=f"Total: {self.total_pieces}"
        )

        self.red_label.config(
            text=f"Rojas: {self.red_pieces}"
        )

        self.blue_label.config(
            text=f"Azules: {self.blue_pieces}"
        )

        self.bad_label.config(
            text=f"Malas: {self.bad_pieces}"
        )

        # Guardar CSV

        try:
            with open(
                self.csv_file,
                mode="a",
                newline="",
                encoding="utf-8"
            ) as file:
                writer = csv.writer(file)
                writer.writerow([
                    date,
                    time,
                    color,
                    result
                ])
        except OSError as error:
            # El registro en consola permite detectar el fallo sin
            # detener el ciclo de cámara ni la interfaz.
            print(f"ERROR guardando el CSV: {error}")

        print(f"{time} | {color} | {result}")

    # ========================================================
    # CERRAR SISTEMA
    # ========================================================

    def close_system(self):
        self.closing = True

        if self.camera is not None:
            try:
                self.camera.release()
            except Exception as error:
                print(f"Error cerrando la cámara: {error}")
            finally:
                self.camera = None

        if self.serial_connection is not None:
            try:
                self.serial_connection.close()
            except Exception as error:
                print(f"Error cerrando el puerto serie: {error}")
            finally:
                self.serial_connection = None

        self.root.destroy()


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = ProductionSystem(
        root
    )

    root.mainloop()
