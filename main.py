from odoo.Odoo import Odoo
from logs.Log import Log

from GenerateHtml import GenerateHtml

log = Log("Generate Odoo Model Documentation")
odoo = Odoo()


if __name__ == '__main__':
    log.info(f"Connecting to Odoo")
    odoo.connect({
        Odoo.URL: "https://prod:Pr0d@odoo.exem.fr",
        Odoo.DB_NAME: 'exem',
        Odoo.USER: "script@exem.fr",
        Odoo.PASSWORD: "Q9f9W@x5X@w<2u"
    })

    model_ids = odoo.getIds("ir.model", [])
    model_fields = odoo.getFields("ir.model", model_ids, ["name", "model", "info", "state", "modules"])
    models = [model["model"] for model in model_fields]

    models_folder = f"models"

    html = GenerateHtml(models, models_folder)

    models_html = html.generate_nav(html.generate_nav_keys(models, False, models_folder))

    html.generate_main_index(models_html, odoo.getFieldsName("ir.model"))
    html.generate_models_index(odoo, model_fields)
