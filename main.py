import io
from itertools import product, tee
from math import ceil
from zipfile import ZipFile

import ezdxf
from flask import Flask, render_template, request, send_file
import numpy as np
import pandas as pd

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def pairwise(iterable):
    # pairwise('ABCDEFG') --> AB BC CD DE EF FG
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


@app.route("/", methods=["GET", "POST"])
def index():
    return render_template("index.html", error="")


@app.route("/convert", methods=["GET", "POST"])
def convert():
    if request.method == "POST":
        try:
            f = request.files.get("file")
            filename, extension = f.filename.replace(" ", "_").rsplit(".", 1)
            if not extension.lower() == "dxf":
                raise ezdxf.DXFTypeError
            buffer = io.BytesIO(f.read())
            wrapper = io.TextIOWrapper(buffer, encoding="utf-8")
            doc = ezdxf.read(wrapper)
        except (ezdxf.DXFTypeError, UnicodeDecodeError, ValueError):
            return render_template(
                "index.html", error="Wybierz plik w formacie DXF minimum 2007."
            )
        except ezdxf.DXFStructureError:
            return render_template("index.html", error="Niepoprawny lub zepsuty plik.")
        except Exception as e:
            return render_template("index.html", error=str(e))
        msp = doc.modelspace()
        for polyline in msp.query("LWPOLYLINE"):
            polyline.explode()
        start = pd.DataFrame([[*line.dxf.start] for line in msp.query("LINE")])
        end = pd.DataFrame([[*line.dxf.end] for line in msp.query("LINE")])
        nodes = pd.concat([start, end], ignore_index=True).round(3)
        if len(nodes.index) == 0:
            return render_template("index.html", error="Nieprawidłowa geometria.")
        nodes.columns = ["X", "Y", "Z"]
        nodes.name = f"Wezly-{filename}.txt"
        elements = pd.DataFrame(
            [(n, n + len(start), 0, 0, 0) for n in range(1, len(start) + 1)]
        )
        elements.columns = ["wI", "wJ", "wK", "Kier", "Mat"]
        elements["Prz"] = pd.DataFrame([[line.dxf.color] for line in msp.query("LINE")])
        elements["Prz"].replace({256: 0}, inplace=True)
        elements.name = f"Prety-{filename}.txt"
        if request.form["b"] == "Płaskie":
            dxf_units = {
                4: 1e-1,  # Millimeters
                5: 1e0,  # Centimeters
                6: 1e2,  # Meters
                7: 1e5,  # Kilometers
            }
            g = float(request.form["g"])
            mesh = {}
            for column in nodes.columns:
                positions = nodes[column].sort_values().unique()
                if all(positions == 0):
                    mesh[column] = np.zeros(1)
                else:
                    mesh[column] = np.empty(0)
                    for x, y in pairwise(positions):
                        mesh[column] = np.append(
                            mesh[column],
                            np.linspace(
                                x, y, ceil((y - x) / (g / dxf_units.get(doc.units)) + 1)
                            ),
                        )
            mesh = (
                pd.DataFrame(sorted(product(*mesh.values())), columns=nodes.columns)
                .round(3)
                .drop_duplicates()
                .reset_index(drop=True)
            )
            mesh.name = f"Wezly-{filename}.txt"
            c = mesh.value_counts("X").min()
            flats = pd.DataFrame(
                [
                    (n, n + 1, n + c + 1, n + c, 0, g / dxf_units[6])
                    for n in range(1, len(mesh) + 1)
                ]
            )
            flats = flats.drop(flats.index[c - 1 :: c]).reset_index(drop=True)[: -c + 1]
            flats.columns = ["w1", "w2", "w3", "w4", "w5", "g"]
            flats.name = f"Plaskie-{filename}.txt"
        files = {}
        for df in [nodes, elements] if request.form["b"] == "Rama3D" else [mesh, flats]:
            df.index += 1
            with io.StringIO() as buffer:
                df.to_csv(buffer, sep=" ", decimal=",", line_terminator="\r\n")
                mem = io.BytesIO()
                mem.write(buffer.getvalue().encode())
                mem.seek(0)
                files[df.name] = mem
        output = io.BytesIO()
        with ZipFile(output, "w") as zip_file:
            for name, mem in files.items():
                zip_file.writestr(name, mem.getvalue())
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name=f"{filename}.zip",
        )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False)
