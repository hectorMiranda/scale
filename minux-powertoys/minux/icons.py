"""Small vector icons drawn directly onto a Tk Canvas.

Drawing the icons as vectors (rather than using emoji or image files) keeps them
crisp at any size, scales them with the app's text size, and sidesteps the fact
that classic Tk on Windows can't render colour emoji. Each icon is defined in a
24x24 coordinate space and scaled to the requested pixel size.

``draw(canvas, name, size, color, accent)`` clears the canvas and renders the
named icon. Unknown names draw nothing.
"""

from __future__ import annotations

BASE = 24.0


def _lw(size: float, w: float = 2.1) -> float:
    return max(1.4, w * size / BASE)


def draw(canvas, name, size, color="#3b3b3b", accent=None) -> None:
    canvas.delete("all")
    fn = _ICONS.get(name)
    if fn is None:
        return
    k = size / BASE

    def P(*coords):  # scale a flat list of 24-space coords to pixels
        return [v * k for v in coords]

    def line(coords, col=color, w=2.1, smooth=False, arrow=None):
        canvas.create_line(*P(*coords), fill=col, width=_lw(size, w),
                           capstyle="round", joinstyle="round", smooth=smooth, arrow=arrow)

    def poly(coords, fill=color, outline="", w=1.6):
        canvas.create_polygon(*P(*coords), fill=fill, outline=outline,
                              width=_lw(size, w), joinstyle="round")

    def oval(x0, y0, x1, y1, col=color, fill="", w=2.1):
        canvas.create_oval(*P(x0, y0, x1, y1), outline=col, fill=fill, width=_lw(size, w))

    def arc(x0, y0, x1, y1, start, extent, col=color, w=2.1, style="arc"):
        canvas.create_arc(*P(x0, y0, x1, y1), start=start, extent=extent,
                         outline=col, width=_lw(size, w), style=style)

    def rect(x0, y0, x1, y1, col=color, fill="", w=2.1):
        canvas.create_rectangle(*P(x0, y0, x1, y1), outline=col, fill=fill, width=_lw(size, w))

    fn(line, poly, oval, arc, rect, color, accent or color)


# --- individual icons -------------------------------------------------------- #
# Each takes the scaled drawing helpers plus the base and accent colours.

def _reset(line, poly, oval, arc, rect, c, a):
    arc(4, 4, 20, 20, start=75, extent=250)          # circular arrow, gap top-right
    poly([16.5, 3.5, 20, 6, 15.5, 8.2], fill=c)       # arrowhead


def _paste(line, poly, oval, arc, rect, c, a):
    rect(5, 5, 19, 21)                                # clipboard body
    rect(9, 3, 15, 6.5)                               # top clip
    line([8, 11, 16, 11]); line([8, 14, 16, 14]); line([8, 17, 13, 17])


def _play(line, poly, oval, arc, rect, c, a):
    poly([7, 5, 7, 19, 19, 12], fill=a)               # right-pointing triangle


def _stop(line, poly, oval, arc, rect, c, a):
    rect(6, 6, 18, 18, col=a, fill=a, w=1.0)


def _clock(line, poly, oval, arc, rect, c, a):
    oval(4, 4, 20, 20)
    line([12, 12, 12, 7]); line([12, 12, 16, 13.5])


def _mouse(line, poly, oval, arc, rect, c, a):
    canvas_rect = rect
    canvas_rect(8, 4, 16, 20)                          # body (rounded-ish)
    line([12, 4, 12, 10])                              # top split
    line([12, 6.5, 12, 9], col=a, w=2.4)               # scroll wheel


def _pencil(line, poly, oval, arc, rect, c, a):
    poly([5, 19, 7, 14, 16, 5, 19, 8, 10, 17], fill="")  # outline body
    line([5, 19, 7, 14, 16, 5, 19, 8, 10, 17, 5, 19])
    line([15, 6, 18, 9])                               # tip band
    line([5, 19, 8, 18], col=a)                        # graphite tip


def _turtle(line, poly, oval, arc, rect, c, a):
    oval(7, 8, 18, 16, fill="")                        # shell
    arc(7, 8, 18, 16, start=0, extent=180)             # shell dome accent
    oval(17, 10, 21, 14)                               # head
    line([9, 16, 8, 19]); line([16, 16, 17, 19])       # legs


def _walk(line, poly, oval, arc, rect, c, a):
    oval(10, 3, 14, 7, fill="")                        # head
    line([12, 7, 12, 14])                              # torso
    line([12, 9, 15, 12]); line([12, 9, 9, 11])        # arms
    line([12, 14, 15, 20]); line([12, 14, 9, 19])      # legs (mid-stride)


def _rabbit(line, poly, oval, arc, rect, c, a):
    oval(8, 11, 17, 20, fill="")                       # head/body
    line([10, 11, 8.5, 3.5, 11, 10], smooth=True)      # left ear
    line([14, 11, 15.5, 3.5, 13, 10], smooth=True)     # right ear
    oval(11.5, 14.5, 13, 16, col=a, fill=a, w=1.0)     # nose


def _bolt(line, poly, oval, arc, rect, c, a):
    poly([13, 3, 6, 13, 11, 13, 9, 21, 18, 10, 12, 10], fill=a)


def _keyboard(line, poly, oval, arc, rect, c, a):
    rect(3, 7, 21, 18)
    for x in (6, 9, 12, 15, 18):
        line([x, 10, x, 10.3], w=2.4)
    for x in (7.5, 10.5, 13.5, 16.5):
        line([x, 13, x, 13.3], w=2.4)
    line([8, 16, 16, 16], w=2.4)                        # space bar


def _gauge(line, poly, oval, arc, rect, c, a):
    arc(4, 6, 20, 22, start=20, extent=140)            # speedometer arc
    line([12, 18, 16, 10], col=a)                      # needle


def _zoomin(line, poly, oval, arc, rect, c, a):
    oval(4, 4, 15, 15)                                 # magnifier lens
    line([13.5, 13.5, 20, 20], w=2.7)                  # handle
    line([9.5, 7, 9.5, 12], col=a); line([7, 9.5, 12, 9.5], col=a)  # plus


def _zoomout(line, poly, oval, arc, rect, c, a):
    oval(4, 4, 15, 15)
    line([13.5, 13.5, 20, 20], w=2.7)
    line([7, 9.5, 12, 9.5], col=a)                     # minus


_ICONS = {
    "reset": _reset, "paste": _paste, "play": _play, "stop": _stop,
    "clock": _clock, "mouse": _mouse, "pencil": _pencil, "turtle": _turtle,
    "walk": _walk, "rabbit": _rabbit, "bolt": _bolt, "keyboard": _keyboard,
    "gauge": _gauge, "zoomin": _zoomin, "zoomout": _zoomout,
}
