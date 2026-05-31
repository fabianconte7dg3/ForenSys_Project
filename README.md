# ForenSys Project 🔬🛡️

Desarrollo de una herramienta compacta y de bajo costo para la adquisición y análisis inmediato de evidencia digital en el lugar de los hechos.

## Descripción

ForenSys es un sistema innovador de investigación forense digital que aprovecha la potencia de la **Raspberry Pi 5** para ejecutar modelos ligeros de IA. La herramienta automatiza:

- 🔍 Detección de patrones
- 📂 Clasificación de archivos
- ⚠️ Búsqueda de anomalías en discos
- 🌐 Búsqueda de anomalías en redes

## Características Principales

✅ **Compacto y portátil** - Diseñado para funcionar en Raspberry Pi 5
✅ **Bajo costo** - Solución económica para investigación forense
✅ **Análisis inmediato** - Adquisición y procesamiento en tiempo real
✅ **IA Optimizada** - Modelos ligeros para detección de patrones
✅ **Análisis digital integral** - Cobertura de sistemas de archivos y redes

## Requisitos

- Raspberry Pi 5
- Python 3.7+
- Librerías de machine learning ligeras
- Permisos de administrador para análisis de discos

## Instalación (Desde Cero)

En una Raspberry Pi 5 con un sistema recién instalado (Ubuntu/Raspberry Pi OS), solo debes ejecutar los siguientes comandos:

```bash
# 1. Clonar el repositorio
git clone https://github.com/fabianconte7dg3/ForenSys_Project.git
cd ForenSys_Project

# 2. Ejecutar el instalador automático
sudo bash scripts/kiosk/install_services.sh

# 3. Reiniciar el sistema
sudo reboot
```

## Uso

Al reiniciar, ForenSys arrancará **automáticamente en modo kiosko** a pantalla completa mostrando la interfaz web (Dashboard).

Para tareas de mantenimiento vía SSH o si sales al escritorio, ahora dispones del comando global `kiosk`:

```bash
kiosk start    # Inicia la web app y el modo kiosko
kiosk stop     # Detiene el modo kiosko
kiosk status   # Verifica si los servicios están corriendo
```

## Estructura del Proyecto

```
ForenSys_Project/
├── README.md
├── requirements.txt
├── src/
│   ├── acquisition/      # Módulos de adquisición digital
│   ├── analysis/         # Análisis y detección de patrones
│   ├── ml_models/        # Modelos de IA ligeros
│   └── utils/            # Funciones auxiliares
├── tests/                # Pruebas unitarias
└── docs/                 # Documentación
```

## Composición del Proyecto

- **Python**: 97.7% 🐍
- **C**: 1.0% ⚙️
- **HTML**: 0.6% 🌐
- **Cython**: 0.3%
- **C++**: 0.2%
- **Fortran**: 0.1%
- **Otro**: 0.1%

## Contribuciones

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## Licencia

Este proyecto está bajo la licencia MIT. Ver el archivo `LICENSE` para más detalles.

## Autor

**Fabian Conte**

## Contacto

Para preguntas, sugerencias o reportar bugs, abre un issue en el repositorio.

---

**ForenSys** - Investigación Forense Digital Inteligente 🔬
