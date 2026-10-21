"""
Mini línea de producción: detección y clasificación de piezas rojas y azules.
Requisitos:
    pip install opencv-python numpy pillow
Para usar ESP32:
    pip install pyserial
"""

import csv
import os
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import cv2
import numpy as np
from PIL import Image, ImageTk

# --------------------------- CONFIGURACIÓN ---------------------------
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
MIN_OBJECT_AREA = 5000
MIN_SATURATION = 30
CLASSIFICATION_DELAY = 1.5
NO_PIECE_RESET_FRAMES = 12
CAMERA_RETRY_MS = 1500
VIDEO_REFRESH_MS = 30

# Valores HSV de referencia (OpenCV: H=0..179, S/V=0..255).
# Ajusta estos valores con la iluminación y las piezas reales.
RED_REFERENCE = np.array([0, 200, 200], dtype=np.float32)
BLUE_REFERENCE = np.array([110, 200, 200], dtype=np.float32)
# Tolerancias amplias para una demostración. Aceptan variaciones de tono,
# saturación y brillo; con iluminación muy distinta aún puede requerir ajuste.
RED_TOLERANCE = np.array([18, 150, 150], dtype=np.float32)
BLUE_TOLERANCE = np.array([25, 150, 150], dtype=np.float32)

# Dejar False para probar sin hardware. Cambiar a True para usar ESP32.
ESP32_ENABLED = False
ESP32_PORT = "COM3"
ESP32_BAUDRATE = 115200

try:
    import serial
except ImportError:
    serial = None


class ProductionSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("Mini Línea de Producción")
        self.root.geometry("1050x720")
        self.root.minsize(900, 620)
        self.root.protocol("WM_DELETE_WINDOW", self.close_system)

        self.system_running = False
        self.closing = False
        self.camera = None
        self.serial_connection = None
        self.csv_file = Path(__file__).resolve().with_name("registro_produccion.csv")

        self.total_pieces = 0
        self.red_pieces = 0
        self.blue_pieces = 0
        self.bad_pieces = 0
        self.processing_piece = False
        self.no_piece_frames = 0
        self.last_classification_time = 0.0
        self.pending_piece_result = None
        self.pending_piece_color = None
        self.piece_seen_frames = 0
        self.PIECE_CONFIRM_FRAMES = 3
        self.last_result = "SIN CLASIFICAR"

        self.create_csv()
        self.create_interface()
        self.connect_esp32()
        self.open_camera()
        self.update_camera()

    # --------------------------- CSV ---------------------------
    def create_csv(self):
        try:
            if not self.csv_file.exists() or self.csv_file.stat().st_size == 0:
                with self.csv_file.open("w", newline="", encoding="utf-8-sig") as file:
                    writer = csv.writer(file)
                    writer.writerow(["Fecha", "Hora", "Color detectado", "Resultado"])
        except OSError as error:
            print(f"ERROR creando el CSV: {error}")

    # --------------------------- INTERFAZ ---------------------------
    def create_interface(self):
        title = tk.Label(
            self.root, text="MINI LÍNEA DE PRODUCCIÓN",
            font=("Arial", 22, "bold")
        )
        title.pack(pady=(12, 8))

        main_frame = tk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=12, pady=8)

        self.video_label = tk.Label(
            main_frame, text="Esperando cámara...", bg="#202020",
            fg="white", width=80, height=30
        )
        self.video_label.pack(side="left", padx=(0, 18), pady=5)

        info_frame = tk.Frame(main_frame, padx=8)
        info_frame.pack(side="left", fill="y", pady=5)

        def heading(text):
            tk.Label(info_frame, text=text, font=("Arial", 12, "bold")).pack(pady=(10, 2))

        heading("Estado del sistema")
        self.status_label = tk.Label(info_frame, text="INICIALIZANDO", font=("Arial", 14, "bold"))
        self.status_label.pack()

        heading("Sensor / pieza")
        self.sensor_label = tk.Label(info_frame, text="SIN PIEZA", font=("Arial", 12))
        self.sensor_label.pack()

        heading("Color detectado")
        self.color_label = tk.Label(info_frame, text="---", font=("Arial", 14, "bold"))
        self.color_label.pack()

        heading("Último resultado")
        self.result_label = tk.Label(info_frame, text="SIN CLASIFICAR", font=("Arial", 14, "bold"))
        self.result_label.pack()

        heading("CONTADORES")
        self.total_label = tk.Label(info_frame, text="Total: 0", font=("Arial", 12))
        self.total_label.pack()
        self.red_label = tk.Label(info_frame, text="Rojas: 0", font=("Arial", 12), fg="red")
        self.red_label.pack()
        self.blue_label = tk.Label(info_frame, text="Azules: 0", font=("Arial", 12), fg="blue")
        self.blue_label.pack()
        self.bad_label = tk.Label(info_frame, text="Malas: 0", font=("Arial", 12))
        self.bad_label.pack()

        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=(0, 14))

        self.start_button = tk.Button(
            button_frame, text="INICIAR", font=("Arial", 11, "bold"),
            command=self.start_system, width=13
        )
        self.start_button.grid(row=0, column=0, padx=6)

        self.stop_button = tk.Button(
            button_frame, text="DETENER", font=("Arial", 11, "bold"),
            command=self.stop_system, width=13, state="disabled"
        )
        self.stop_button.grid(row=0, column=1, padx=6)

        tk.Button(
            button_frame, text="REINTENTAR CÁMARA", font=("Arial", 10),
            command=self.retry_camera, width=18
        ).grid(row=0, column=2, padx=6)

        tk.Button(
            button_frame, text="REINICIAR CONTADORES", font=("Arial", 10),
            command=self.reset_counters, width=20
        ).grid(row=0, column=3, padx=6)

    # --------------------------- CÁMARA ---------------------------
    def open_camera(self):
        if self.closing:
            return False
        try:
            camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(CAMERA_INDEX)
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            if not camera.isOpened():
                camera.release()
                self.camera = None
                self.status_label.config(text="ERROR DE CÁMARA")
                self.video_label.config(image="", text="No se pudo abrir la cámara.\nPulsa REINTENTAR CÁMARA.", bg="#202020", fg="white")
                self.video_label.image = None
                return False
            self.camera = camera
            self.status_label.config(text="DETENIDO")
            return True
        except Exception as error:
            self.camera = None
            print(f"Error abriendo cámara: {error}")
            if hasattr(self, "status_label"):
                self.status_label.config(text="ERROR DE CÁMARA")
            return False

    def retry_camera(self):
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        self.open_camera()

    def update_camera(self):
        if self.closing:
            return

        if self.camera is None or not self.camera.isOpened():
            self.status_label.config(text="ERROR DE CÁMARA")
            self.root.after(CAMERA_RETRY_MS, self.update_camera)
            return

        ok, frame = self.camera.read()
        if not ok or frame is None:
            self.status_label.config(text="ERROR DE LECTURA")
            self.root.after(CAMERA_RETRY_MS, self.update_camera)
            return

        processed = self.process_frame(frame)
        rgb = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb).resize((640, 480))
        photo = ImageTk.PhotoImage(image=image)
        self.video_label.configure(image=photo, text="", width=640, height=480)
        self.video_label.image = photo

        self.status_label.config(text="FUNCIONANDO" if self.system_running else "DETENIDO")
        self.root.after(VIDEO_REFRESH_MS, self.update_camera)

    # --------------------------- DETECCIÓN Y CLASIFICACIÓN ---------------------------
    def process_frame(self, frame):
        display = frame.copy()
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Busca zonas saturadas, elimina ruido y cierra pequeños huecos.
        saturation = hsv[:, :, 1]
        _, mask = cv2.threshold(saturation, MIN_SATURATION, 255, cv2.THRESH_BINARY)
        kernel = np.ones((5, 5), dtype=np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_contours = [c for c in contours if cv2.contourArea(c) >= MIN_OBJECT_AREA]

        if not valid_contours:
            self.sensor_label.config(text="SIN PIEZA")
            self.no_piece_frames += 1
            self.piece_seen_frames = 0

            # Contar cuando la pieza ya salió de la zona de cámara.
            # Así se confirma un ciclo completo y se evita contar varias veces
            # mientras la pieza permanece visible.
            if self.no_piece_frames >= NO_PIECE_RESET_FRAMES:
                if self.processing_piece and self.pending_piece_result is not None:
                    self.register_result(self.pending_piece_color, self.pending_piece_result)
                    self.send_to_esp32(self.pending_piece_result)
                    self.show_result(self.pending_piece_result)
                self.processing_piece = False
                self.pending_piece_result = None
                self.pending_piece_color = None

            self.color_label.config(text="---")
            return display

        contour = max(valid_contours, key=cv2.contourArea)
        self.no_piece_frames = 0
        self.piece_seen_frames += 1
        self.sensor_label.config(text="PIEZA DETECTADA")

        x, y, w, h = cv2.boundingRect(contour)
        cv2.rectangle(display, (x, y), (x + w, y + h), (255, 255, 255), 2)

        roi = hsv[y:y + h, x:x + w]
        local_mask = np.zeros((h, w), dtype=np.uint8)
        local_contour = contour.copy()
        local_contour[:, 0, 0] -= x
        local_contour[:, 0, 1] -= y
        cv2.drawContours(local_mask, [local_contour], -1, 255, thickness=cv2.FILLED)
        pixels = roi[local_mask > 0]

        color, result = self.classify_color(pixels)
        self.color_label.config(text=color, fg={"ROJO": "red", "AZUL": "blue"}.get(color, "black"))
        cv2.putText(
            display, f"{color} / {result}", (x, max(25, y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA
        )

        now = time.monotonic()
        if (
            self.system_running
            and not self.processing_piece
            and self.piece_seen_frames >= self.PIECE_CONFIRM_FRAMES
            and now - self.last_classification_time >= CLASSIFICATION_DELAY
        ):
            # Guardar temporalmente la clasificación; el contador se incrementa
            # cuando se confirma que la pieza salió de la cámara.
            self.processing_piece = True
            self.last_classification_time = now
            self.pending_piece_color = color
            self.pending_piece_result = result

        return display

    def classify_color(self, pixels):
        if pixels is None or np.asarray(pixels).size == 0:
            return "OTRO", "MALA"

        pixels = np.asarray(pixels).reshape(-1, 3).astype(np.float32)

        # Media circular del tono HSV: los tonos 179 y 0 son vecinos.
        angles = pixels[:, 0] * (2.0 * np.pi / 180.0)
        mean_sin = np.mean(np.sin(angles))
        mean_cos = np.mean(np.cos(angles))
        hue = (np.arctan2(mean_sin, mean_cos) % (2.0 * np.pi)) * (180.0 / (2.0 * np.pi))
        measured = np.array([hue, np.median(pixels[:, 1]), np.median(pixels[:, 2])], dtype=np.float32)

        # Clasificación flexible para demostración:
        # - Rojo: contempla tonos próximos a 0 y al extremo 179 de HSV.
        # - Azul: acepta un intervalo amplio de tonos azules.
        # - Se evita exigir que saturación y brillo coincidan exactamente con
        #   una única muestra de referencia.
        h, s, v = (float(measured[0]), float(measured[1]), float(measured[2]))

        # El rojo se encuentra a ambos lados del límite del tono HSV.
        red_hue = (h <= 18.0) or (h >= 165.0)
        blue_hue = 85.0 <= h <= 140.0

        # Si el tono es débil, la clasificación por color es poco fiable.
        # Para exposición aceptamos saturación moderada y brillo no extremo.
        visible_color = s >= 35.0 and v >= 35.0

        if visible_color and red_hue:
            return "ROJO", "ROJA"
        if visible_color and blue_hue:
            return "AZUL", "AZUL"

        # Respaldo por proximidad a las referencias con tolerancias amplias.
        red_ok = self.matches_reference(measured, RED_REFERENCE, RED_TOLERANCE)
        blue_ok = self.matches_reference(measured, BLUE_REFERENCE, BLUE_TOLERANCE)
        if red_ok and (not blue_ok or self.color_distance(measured, RED_REFERENCE) <= self.color_distance(measured, BLUE_REFERENCE)):
            return "ROJO", "ROJA"
        if blue_ok:
            return "AZUL", "AZUL"
        return "OTRO", "MALA"

    @staticmethod
    def matches_reference(color, reference, tolerance):
        hue_diff = abs(float(color[0]) - float(reference[0]))
        hue_diff = min(hue_diff, 180.0 - hue_diff)
        sat_diff = abs(float(color[1]) - float(reference[1]))
        val_diff = abs(float(color[2]) - float(reference[2]))
        return hue_diff <= tolerance[0] and sat_diff <= tolerance[1] and val_diff <= tolerance[2]

    @staticmethod
    def color_distance(color, reference):
        diff = np.abs(color.astype(np.float32) - reference.astype(np.float32))
        diff[0] = min(float(diff[0]), 180.0 - float(diff[0]))
        return float(np.sqrt(np.sum(diff ** 2)))

    # --------------------------- CONTROL ---------------------------
    def start_system(self):
        if self.camera is None or not self.camera.isOpened():
            messagebox.showwarning("Cámara no disponible", "Conecta la cámara y pulsa REINTENTAR CÁMARA.")
            return
        self.system_running = True
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.status_label.config(text="FUNCIONANDO")

    def stop_system(self):
        self.system_running = False
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.status_label.config(text="DETENIDO")
        self.sensor_label.config(text="SIN PIEZA")
        self.processing_piece = False
        self.no_piece_frames = 0
        self.pending_piece_result = None
        self.pending_piece_color = None
        self.piece_seen_frames = 0

    def reset_counters(self):
        if not messagebox.askyesno("Confirmar", "¿Deseas reiniciar los contadores de esta sesión?"):
            return
        self.total_pieces = self.red_pieces = self.blue_pieces = self.bad_pieces = 0
        self.update_counter_labels()

    def update_counter_labels(self):
        self.total_label.config(text=f"Total: {self.total_pieces}")
        self.red_label.config(text=f"Rojas: {self.red_pieces}")
        self.blue_label.config(text=f"Azules: {self.blue_pieces}")
        self.bad_label.config(text=f"Malas: {self.bad_pieces}")

    def show_result(self, result):
        self.last_result = result
        self.result_label.config(text=result)

    # --------------------------- REGISTRO ---------------------------
    def register_result(self, color, result):
        now = datetime.now()
        self.total_pieces += 1
        if result == "ROJA":
            self.red_pieces += 1
        elif result == "AZUL":
            self.blue_pieces += 1
        else:
            self.bad_pieces += 1
        self.update_counter_labels()

        try:
            with self.csv_file.open("a", newline="", encoding="utf-8-sig") as file:
                csv.writer(file).writerow([
                    now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), color, result
                ])
        except OSError as error:
            print(f"ERROR guardando el CSV: {error}")

        print(f"{now:%H:%M:%S} | {color} | {result}")

    # --------------------------- ESP32 ---------------------------
    def connect_esp32(self):
        if not ESP32_ENABLED:
            print("ESP32 desactivado: modo cámara/PC.")
            return
        if serial is None:
            messagebox.showwarning(
                "Falta PySerial",
                "Instala PySerial con: pip install pyserial\nEl sistema continuará sin conexión ESP32."
            )
            return
        try:
            self.serial_connection = serial.Serial(ESP32_PORT, ESP32_BAUDRATE, timeout=1)
            time.sleep(2)  # Algunas placas reinician al abrir el puerto serie.
            print(f"ESP32 conectado en {ESP32_PORT}.")
        except Exception as error:
            self.serial_connection = None
            print(f"No se pudo conectar al ESP32: {error}")
            messagebox.showwarning(
                "ESP32 no conectado",
                f"No se pudo abrir {ESP32_PORT}.\nEl sistema continuará sin enviar datos.\n\nDetalle: {error}"
            )

    def send_to_esp32(self, result):
        if not ESP32_ENABLED or self.serial_connection is None:
            return
        try:
            self.serial_connection.write((result + "\n").encode("utf-8"))
        except Exception as error:
            print(f"Error enviando al ESP32: {error}")

    # --------------------------- CIERRE ---------------------------
    def close_system(self):
        if self.closing:
            return
        self.closing = True
        self.system_running = False
        if self.camera is not None:
            try:
                self.camera.release()
            except Exception as error:
                print(f"Error cerrando cámara: {error}")
            self.camera = None
        if self.serial_connection is not None:
            try:
                self.serial_connection.close()
            except Exception as error:
                print(f"Error cerrando puerto serie: {error}")
            self.serial_connection = None
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ProductionSystem(root)
    root.mainloop()
