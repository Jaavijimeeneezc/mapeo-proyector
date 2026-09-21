#!/usr/bin/env python3
"""
Genera en MapMap una cuadricula de ladrillos por MCP, con deformacion en
perspectiva (homografia) y aparejo a tresbolillo, y la hace reaccionar al
audio que suena en Windows (WASAPI loopback: Spotify, YouTube, lo que sea).

    python ladrillos.py grid  --cols 8 --rows 5 --stagger 0.5
    python ladrillos.py audio --fps 20
    python ladrillos.py bench

El token del servidor MCP se lee del log de MapMap; tambien se puede pasar
con --token. MapMap debe estar arrancado con:  MapMap.exe --mcp-port 8765
"""
import argparse, json, re, sys, time
from pathlib import Path

import requests

import os
# El log lo escribe MapMap lanzado desde la shell; en Windows /tmp de MSYS
# es %LOCALAPPDATA%\Temp, que es donde Python lo encuentra.
DEFAULT_LOG = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp", "mapmap.log")


# ───────────────────────────── cliente MCP ─────────────────────────────
class MapMap:
    def __init__(self, port=8765, token=None, log=DEFAULT_LOG):
        # 127.0.0.1 explicito: "localhost" resuelve primero a ::1 en Windows y
        # el servidor solo escucha en IPv4, lo que costaba ~2 s por peticion.
        self.url = f"http://127.0.0.1:{port}/mcp"
        self.token = token or self._token_from_log(log, port)
        self.headers = {"Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                        "Connection": "keep-alive"}
        self._s = requests.Session()          # reutiliza la conexion TCP
        self._id = 0

    @staticmethod
    def _token_from_log(log, port):
        p = Path(log)
        if not p.exists():
            sys.exit(f"No encuentro {log}. Pasa el token con --token.")
        # "MCP server listening on http://localhost: 8765 /mcp (Authorization: Bearer  <uuid> )"
        hits = re.findall(r"Bearer\s+([0-9a-f-]{36})", p.read_text(errors="ignore"))
        if not hits:
            sys.exit("No hay token en el log. Arranca MapMap con --mcp-port.")
        return hits[-1]        # el del arranque mas reciente

    def rpc(self, method, params=None, timeout=10):
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params:
            body["params"] = params
        r = self._s.post(self.url, headers=self.headers, json=body, timeout=timeout)
        r.raise_for_status()
        return r.json()

    def call(self, name, **args):
        res = self.rpc("tools/call", {"name": name, "arguments": args})
        if "error" in res:
            raise RuntimeError(f"{name}: {res['error']}")
        txt = res["result"]["content"][0]["text"]
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            return txt


# ───────────────────────── geometria: homografia ─────────────────────────
def homography(corners):
    """Mapea el cuadrado unitario a 4 puntos (TL, TR, BR, BL)."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = corners
    dx1, dx2, dx3 = x1 - x2, x3 - x2, x0 - x1 + x2 - x3
    dy1, dy2, dy3 = y1 - y2, y3 - y2, y0 - y1 + y2 - y3
    if abs(dx3) < 1e-9 and abs(dy3) < 1e-9:      # caso afin
        a, b, c = x1 - x0, x2 - x1, x0
        d, e, f = y1 - y0, y2 - y1, y0
        g = h = 0.0
    else:
        den = dx1 * dy2 - dy1 * dx2
        g = (dx3 * dy2 - dy3 * dx2) / den
        h = (dx1 * dy3 - dy1 * dx3) / den
        a, b, c = x1 - x0 + g * x1, x3 - x0 + h * x3, x0
        d, e, f = y1 - y0 + g * y1, y3 - y0 + h * y3, y0

    def P(u, v):
        w = g * u + h * v + 1.0
        return ((a * u + b * v + c) / w, (d * u + e * v + f) / w)
    return P


def brick_quads(cols, rows, corners, stagger=0.0, joint=0.06):
    """Devuelve [(fila, col, [4 vertices])] recortando los medios ladrillos."""
    P = homography(corners)
    out = []
    for j in range(rows):
        off = (j % 2) * stagger / cols
        for i in range(-1, cols):
            u0, u1 = i / cols + off, (i + 1) / cols + off
            if u1 <= 1e-6 or u0 >= 1 - 1e-6:
                continue
            u0, u1 = max(0.0, u0), min(1.0, u1)
            v0, v1 = j / rows, (j + 1) / rows
            mu, mv = (u1 - u0) * joint, (v1 - v0) * joint   # junta de mortero
            au, bu = u0 + mu, u1 - mu
            av, bv = v0 + mv, v1 - mv
            # Orden por FILAS (TL, TR, BL, BR): MapMap crea un Mesh 2x2 y
            # numera asi sus vertices. En sentido horario salen "mariposas".
            out.append((j, max(i, 0),
                        [P(au, av), P(bu, av), P(au, bv), P(bu, bv)]))
    return out


# ───────────────────────────── comandos ─────────────────────────────
def cmd_grid(mm, a):
    w, h = a.canvas
    cor = [(a.corners[k] * w, a.corners[k + 1] * h) for k in range(0, 8, 2)]
    quads = brick_quads(a.cols, a.rows, cor, a.stagger, a.joint)

    if a.clear:
        mm.call("clear_project")
    src = mm.call("create_color_source", color=a.color)
    sid = src["id"]
    print(f"Fuente de color {a.color} -> id {sid}")
    print(f"Creando {len(quads)} ladrillos ({a.cols}x{a.rows}, aparejo {a.stagger})...")

    t0 = time.perf_counter()
    ids = []
    for (row, col, pts) in quads:
        lay = mm.call("create_layer", source_id=sid, shape="quad")
        lid = lay["id"]
        mm.call("set_vertices", id=lid,
                vertices=[{"x": round(x, 2), "y": round(y, 2)} for x, y in pts])
        mm.call("set_property", kind="layer", id=lid,
                property="name", value=f"ladrillo r{row}c{col}")
        ids.append(lid)
    dt = time.perf_counter() - t0

    Path(a.state).write_text(json.dumps(
        {"source": sid, "layers": ids, "cols": a.cols, "rows": a.rows,
         "bricks": [{"id": i, "row": r, "col": c}
                    for i, (r, c) in zip(ids, [(q[0], q[1]) for q in quads])]},
        indent=1), encoding="utf-8")
    print(f"Listo en {dt:.1f} s ({dt/len(quads)*1000:.0f} ms por ladrillo)")
    print(f"Ids guardados en {a.state}")


def cmd_bench(mm, a):
    """Mide cuantas actualizaciones de opacidad por segundo aguanta el MCP."""
    ids = json.loads(Path(a.state).read_text())["layers"]
    n = min(len(ids), a.n)
    t0 = time.perf_counter()
    for k in range(n):
        mm.call("set_property", kind="layer", id=ids[k], property="opacity",
                value=round(0.2 + 0.8 * (k % 5) / 4, 3))
    dt = time.perf_counter() - t0
    print(f"{n} set_property en {dt*1000:.0f} ms  ->  {n/dt:.0f} llamadas/s")
    print(f"Con {len(ids)} ladrillos eso da {n/dt/len(ids):.1f} fps de refresco completo")


def cmd_audio(mm, a):
    import numpy as np
    import pyaudiowpatch as pa

    state = json.loads(Path(a.state).read_text())
    ids = state["layers"]
    bricks = state.get("bricks") or [{"id": i, "row": 0, "col": k}
                                     for k, i in enumerate(ids)]
    cols = state.get("cols", max(b["col"] for b in bricks) + 1)

    # Que banda del espectro mira cada ladrillo.
    #   eq     -> por columna: ecualizador vertical, lo mas legible
    #   spread -> una banda distinta por ladrillo
    #   level  -> todos siguen el nivel general (parpadeo al unisono)
    if a.mode == "eq":
        nb = cols
        band_of = [b["col"] % cols for b in bricks]
    elif a.mode == "level":
        nb = 1
        band_of = [0] * len(bricks)
    else:
        nb = len(ids)
        band_of = list(range(len(ids)))

    p = pa.PyAudio()
    dev = p.get_default_wasapi_loopback()
    sr, ch = int(dev["defaultSampleRate"]), dev["maxInputChannels"]
    chunk = 1024
    stream = p.open(format=pa.paFloat32, channels=ch, rate=sr, input=True,
                    input_device_index=dev["index"], frames_per_buffer=chunk)
    print(f"Escuchando: {dev['name'][:50]}")
    print(f"Modulando {nb} ladrillos a {a.fps} fps. Ctrl+C para parar.\n")

    n = 2048
    win = np.hanning(n)
    # Hasta 6 kHz: por encima la musica casi no tiene energia y esos
    # ladrillos se quedarian siempre apagados.
    edges = np.geomspace(40, min(a.fmax, sr / 2), nb + 1)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    masks = [(freqs >= edges[k]) & (freqs < edges[k + 1]) for k in range(nb)]
    smooth = np.zeros(nb)
    peaks = np.full(nb, 1e-3)      # maximo reciente de CADA banda (AGC)
    period = 1.0 / a.fps
    silent_since = None

    try:
        while True:
            t0 = time.perf_counter()
            # Quedarse con el audio MAS RECIENTE: el stream acumula 48 kHz y
            # el bucle va a 15-25 fps, asi que hay que vaciar lo pendiente.
            raw = stream.read(chunk, exception_on_overflow=False)
            avail = stream.get_read_available()
            while avail >= chunk:
                raw = stream.read(chunk, exception_on_overflow=False)
                avail -= chunk
            x = np.frombuffer(raw, dtype=np.float32).reshape(-1, ch).mean(axis=1)
            if len(x) < n:
                x = np.pad(x, (0, n - len(x)))
            spec = np.abs(np.fft.rfft(x[:n] * win))
            vals = np.array([spec[m].mean() if m.any() else 0.0 for m in masks])

            if vals.max() < 1e-5:                     # silencio real
                silent_since = silent_since or time.time()
                if time.time() - silent_since > 2:
                    print("\r(silencio: no sale audio por esa salida)   ", end="")
                vals = np.zeros(nb)
            else:
                silent_since = None
                # Cada banda se normaliza contra su propio maximo reciente,
                # que decae poco a poco: asi los agudos, mucho mas debiles,
                # tambien llegan a encenderse del todo.
                peaks = np.maximum(vals, peaks * a.agc)
                vals = np.clip((vals / peaks) ** a.curve * a.gain, 0, 1)

            smooth = np.maximum(vals, smooth * a.decay)   # ataque rapido, caida suave

            if silent_since is None:
                bar = "".join("#" if v > .6 else ("+" if v > .3 else
                              ("-" if v > .1 else " ")) for v in smooth[:60])
                print(f"\r|{bar}|", end="")

            for b, k in zip(bricks, band_of):
                v = smooth[k]
                mm.call("set_property", kind="layer", id=b["id"], property="opacity",
                        value=round(float(a.floor + (1 - a.floor) * v), 3), timeout=2)

            time.sleep(max(0, period - (time.perf_counter() - t0)))
    except KeyboardInterrupt:
        print("\nParado.")
    finally:
        stream.close(); p.terminate()
        # Devolver los ladrillos a plena opacidad: si se sale con el brillo
        # al minimo, MapMap queda casi negro y parece que se ha roto algo.
        for b in bricks:
            try:
                mm.call("set_property", kind="layer", id=b["id"],
                        property="opacity", value=1.0, timeout=2)
            except Exception:
                pass


# ───────────────────────────── cli ─────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--token")
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--state", default="ladrillos_ids.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("grid", help="crear la cuadricula de ladrillos")
    g.add_argument("--cols", type=int, default=8)
    g.add_argument("--rows", type=int, default=5)
    g.add_argument("--stagger", type=float, default=0.5, help="aparejo (0-1 ladrillo)")
    g.add_argument("--joint", type=float, default=0.06, help="junta de mortero")
    g.add_argument("--color", default="#ffc23d")
    g.add_argument("--canvas", type=int, nargs=2, default=[640, 480])
    g.add_argument("--corners", type=float, nargs=8,
                   default=[.10, .15, .90, .15, .90, .85, .10, .85],
                   help="TL TR BR BL normalizados: x0 y0 x1 y1 x2 y2 x3 y3")
    g.add_argument("--no-clear", dest="clear", action="store_false")
    g.set_defaults(func=cmd_grid)

    b = sub.add_parser("bench", help="medir el ritmo del MCP")
    b.add_argument("-n", type=int, default=40)
    b.set_defaults(func=cmd_bench)

    a = sub.add_parser("audio", help="modular los ladrillos con el audio del sistema")
    a.add_argument("--fps", type=float, default=20)
    a.add_argument("--mode", choices=["eq", "spread", "level"], default="eq",
                   help="eq: banda por columna | spread: una por ladrillo | level: al unisono")
    a.add_argument("--gain", type=float, default=1.25)
    a.add_argument("--curve", type=float, default=1.6, help="contraste (mas alto = mas seco)")
    a.add_argument("--agc", type=float, default=0.995, help="caida del maximo por banda")
    a.add_argument("--decay", type=float, default=0.72)
    a.add_argument("--fmax", type=float, default=6000)
    a.add_argument("--floor", type=float, default=0.02, help="brillo minimo")
    a.set_defaults(func=cmd_audio)

    args = ap.parse_args()
    mm = MapMap(args.port, args.token, args.log)
    args.func(mm, args)


if __name__ == "__main__":
    main()
