# Portafolio de Raúl Pérez Chávez

**Sitio publicado:** <https://lcervantes27.github.io/raul-portfolio/>

Reconstrucción estática del portafolio publicado originalmente en
[uxfol.io/raul.perez.chz](https://uxfol.io/raul.perez.chz).

## Créditos

- **Contenido, imágenes, casos de estudio y diseño original:** Raúl Pérez Chávez
  ([LinkedIn](https://www.linkedin.com/in/raul-perez-chavez/))
- **Sitio original:** <https://uxfol.io/raul.perez.chz> (alojado en la plataforma uxfol.io)
- **Reconstrucción:** realizada con autorización expresa del autor.

## Sobre esta reconstrucción

El sitio original se sirve como una aplicación JavaScript: su HTML público
apenas pesa unos kilobytes y el contenido real se inyecta por JavaScript desde
la API de la plataforma. Por eso no es posible "guardar la página" para
copiarla.

Este repositorio contiene una **reconstrucción en HTML/CSS estático** generada a
partir del contenido público del portafolio. Es importante ser preciso sobre el
alcance:

- El código de este sitio (HTML, CSS y el generador) fue **escrito desde cero**.
- **No incluye ni reutiliza el código, las plantillas, el bundle JavaScript ni el
  CSS de uxfol.io.** Esos elementos son propiedad de la plataforma y quedan
  fuera de lo que el autor del portafolio puede autorizar.
- La reconstrucción no es un clon pixel a pixel de la plantilla original: es una
  reinterpretación limpia de su contenido y su estructura.

## Estructura

```
.
├── index.html          # Página principal
├── casos/              # Un archivo HTML por caso de estudio (6)
├── assets/
│   ├── css/style.css   # Hoja de estilos propia
│   └── img/            # Imágenes del portafolio (165 archivos)
├── data/content.json   # Contenido depurado del que se genera el sitio
└── build/generate.py   # Generador del sitio (Python, sin dependencias)
```

## Cómo se regenera

```bash
python3 build/generate.py
```

El generador lee `data/content.json` y produce todas las páginas. Para volver a
partir del volcado original del contenido, se le puede indicar otra fuente:

```bash
python3 build/generate.py --source /ruta/al/portfolio-data.json
```

## Notas

- **Peso del repositorio.** Las imágenes suman ~97 MB. La mayor parte son ocho
  GIFs de entre 5 y 10 MB que documentan prototipos en movimiento; son
  contenido real del portafolio, no restos de la descarga. Ningún archivo
  suelto supera los 10 MB.
- **Vídeos.** Quince secciones incrustan vídeos de YouTube mediante `iframe`.
  Para verlos hay que servir el sitio por HTTP (por ejemplo
  `python3 -m http.server`); abierto directamente como `file://` YouTube
  rechaza la reproducción por falta de referente.
- **Tipografías.** Se cargan Inter, Sora y Bricolage Grotesque desde Google
  Fonts, las tres familias que usa el diseño original.
