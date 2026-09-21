# Mapeo proyector

Video mapping sobre una pared de ladrillo, controlando MapMap por su API MCP.

`ladrillos.py` genera la cuadrícula de ladrillos con corrección de
perspectiva por homografía y aparejo a tresbolillo, y después la hace
reaccionar en tiempo real al audio que suena en el PC, capturado por WASAPI
en modo loopback.

## Uso

```
python ladrillos.py grid  --cols 8 --rows 5 --stagger 0.5
python ladrillos.py audio --fps 20
python ladrillos.py bench
```

MapMap debe estar arrancado con el servidor MCP activo:

```
MapMap.exe --mcp-port 8765
```

## Contenido

- `ladrillos.py` — generador de la cuadrícula y motor de reacción al audio.
- `mapeo.html` — visor web del mapeo.
- `ladrillos.mmp` — proyecto de MapMap.
- `ladrillos_ids.json` — correspondencia entre ladrillos e identificadores.
- `build-mapmap.sh` — compilación de MapMap desde fuentes.

## Licencia

MIT. Ver `LICENSE`.
