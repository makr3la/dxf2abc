import io
from zipfile import ZipFile

import ezdxf
from flask import Flask, render_template, request, send_file
import pandas as pd

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


@app.route("/", methods=["GET", "POST"])
def index():
    return render_template("index.html", error="")


@app.route("/convert", methods=["GET", "POST"])
def convert():
    if request.method == "POST":
        try:
            f = request.files.get("file")
            buffer = io.BytesIO(f.read())
            wrapper = io.TextIOWrapper(buffer, encoding="utf-8")
            doc = ezdxf.read(wrapper)
        except ezdxf.DXFStructureError:
            return render_template("index.html", error="Invalid or corrupted DXF file.")
        except Exception as e:
            return render_template("index.html", error=str(e))
        msp = doc.modelspace()
        for polyline in msp.query("LWPOLYLINE"):
            polyline.explode()
        start = pd.DataFrame([[*line.dxf.start] for line in msp.query("LINE")])
        end = pd.DataFrame([[*line.dxf.end] for line in msp.query("LINE")])
        nodes = pd.concat([start, end], ignore_index=True)
        nodes.name = "Węzły.txt"
        elements = pd.DataFrame(
            [(n, n + len(start), 0, 0, 0, 0) for n in range(1, len(start) + 1)]
        )
        elements.name = "Pręty.txt"
        files = {}
        for df in [nodes, elements]:
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
            attachment_filename=f"{f.filename.split('.')[0]}.zip",
        )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False)
