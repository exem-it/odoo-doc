import glob
import os
import shutil


SITE_DIR = "_site"


def discover_doc_dirs():
    return sorted(
        path
        for path in glob.glob("docs*")
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "index.html"))
    )


def build_root_index(doc_dirs):
    links = "\n".join(f'    <li><a href="{name}/">{name}</a></li>' for name in doc_dirs)
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Documentation Odoo</title>
</head>
<body>
  <h1>Documentation Odoo</h1>
  <p>Choisissez une version :</p>
  <ul>
{links}
  </ul>
</body>
</html>
"""


def touch_nojekyll(directory):
    with open(os.path.join(directory, ".nojekyll"), "w", encoding="utf-8"):
        pass


def build_site():
    doc_dirs = discover_doc_dirs()
    if not doc_dirs:
        raise SystemExit("No docs* folder with index.html found at repository root.")

    if os.path.exists(SITE_DIR):
        shutil.rmtree(SITE_DIR)
    os.makedirs(SITE_DIR)

    for name in doc_dirs:
        destination = os.path.join(SITE_DIR, name)
        shutil.copytree(name, destination)
        touch_nojekyll(destination)

    with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as file:
        file.write(build_root_index(doc_dirs))

    touch_nojekyll(SITE_DIR)

    print(f"Built GitHub Pages site in {SITE_DIR}/ with: {', '.join(doc_dirs)}")


if __name__ == "__main__":
    build_site()
