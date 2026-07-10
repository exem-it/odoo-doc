from Log import Log
from Odoo import Odoo

from GenerateHtml import GenerateHtml
from GenerateSql import GenerateSql

log = Log("Generate Odoo Model Documentation")
odoo = Odoo()


if __name__ == '__main__':
    log.info(f"Connecting to Odoo")
    odoo.connect({
        Odoo.URL: "https://lab:xgJWh83nUJ2ATMRzteqTLHyoujAmci@odoo-test.exem.fr",
        Odoo.DB_NAME: "exem",
        Odoo.USER: "script@exem.fr",
        Odoo.PASSWORD: "Q9f9W@x5X@w<2u"
    })

    model_ids = odoo.get_ids("ir.model")
    model_fields = odoo.get_fields("ir.model", model_ids, ["name", "model", "info", "state", "modules"])
    models = [model["model"] for model in model_fields]

    models_folder = f"models"

    html = GenerateHtml(models, models_folder, "docs12")
    sql = GenerateSql(html.main_folder)

    models_html = html.generate_nav(html.generate_nav_keys(models, False, models_folder))

    html.generate_main_index(models_html, odoo.get_fields_name("ir.model"))
    html.generate_models_index(odoo, model_fields, sql)
    sql.write()
