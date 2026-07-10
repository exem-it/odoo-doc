import os
import shutil

from Log import Log


class GenerateHtml:
    def __init__(self, nav_elements, models_folder, main_folder):
        self.log = Log("GenerateHtml")
        self.main_folder = main_folder
        self.template = open("docs/template.html", "r", encoding="utf-8").read()
        self.nav_elements = nav_elements
        self.models_folder = models_folder
        self.output_folder = f"{self.main_folder}/{models_folder}"
        self.assets_folder = f"{self.main_folder}/assets"

        if not os.path.exists(self.assets_folder):
            shutil.copytree("docs/assets", self.assets_folder)

        if os.path.exists(self.output_folder):
            shutil.rmtree(self.output_folder)
        os.makedirs(self.output_folder, exist_ok=True)

    def generate_content(self, fields, model_name):
        content = f"<h2>{model_name}</h2>\n"
        self.log.info(f"{model_name}: {len(fields.keys())}")
        for key in fields.keys():
            field_value = fields[key]
            content += f"<section id=\"{key}\" class=\"card card-body\">\n"
            content += f"<h4 class=\"card-title\">{key}</h4>\n"
            content += f"<p>\n"
            for parameter_key in field_value:
                parameter_value = field_value[parameter_key]
                if parameter_value is None:
                    continue
                html_value = parameter_value
                if self.nav_elements.__contains__(parameter_value):
                    html_value = f"<a class=\"nav-link\" href=\"../{parameter_value.replace('.', '_')}/index.html\">{parameter_value}</a>"
                content += f"<strong>{parameter_key}:</strong> {html_value}<br>\n"
            content += f"</p>\n</section>\n\n"
        return content

    def generate_nav(self, links):
        nav_html = ""
        for link in links:
            nav_html += f"<li class=\"nav-item\"><a class=\"nav-link\" href=\"{link['path']}\">{link['key']}</a></li>\n"
        return nav_html

    def generate_main_index(self, models_html, model_fields):
        main_html = self.template.replace("</HERE NAVIGATION>", models_html)
        main_html = main_html.replace("</HERE CONTENT>", self.generate_content(model_fields, "ir.model"))
        with open(f"{self.main_folder}/index.html", "w", encoding="utf-8") as f:
            f.write(main_html)

    def get_model_fields(self, odoo, model_name):
        try:
            return odoo.get_fields_name(model_name)
        except BaseException as error:
            self.log.warning(f"{model_name}: fields_get failed, using ir.model.fields fallback ({error})")
            return self._fields_from_ir_model_fields(odoo, model_name)

    def _fields_from_ir_model_fields(self, odoo, model_name):
        field_records = odoo.get_fields_by_conditions(
            "ir.model.fields",
            [("model", "=", model_name)],
            ["name", "ttype", "field_description", "help", "relation", "required", "readonly", "store", "selection"],
        )
        fields = {}
        for record in field_records:
            field_info = {
                "type": record.get("ttype", ""),
                "string": record.get("field_description", ""),
                "help": record.get("help") or "",
                "required": record.get("required", False),
                "readonly": record.get("readonly", False),
                "store": record.get("store", True),
            }
            if record.get("relation"):
                field_info["relation"] = record["relation"]
            if record.get("selection"):
                field_info["selection"] = record["selection"]
            fields[record["name"]] = field_info
        return fields

    def render_model_page(self):
        return self.template.replace("assets", "../../assets")

    def generate_models_index(self, odoo, model_fields, sql=None):
        for model in model_fields:
            model_name = model["model"]
            model_folder = model_name.replace(".", "_")
            pages_html = self.render_model_page()
            try:
                fields = self.get_model_fields(odoo, model_name)
                if sql is not None:
                    sql.add_model(model_name, fields)
                fields_keys = self.generate_nav_keys(fields.keys())
                pages_html = pages_html.replace("</HERE NAVIGATION>", self.generate_nav(fields_keys))
                pages_html = pages_html.replace("</HERE CONTENT>", self.generate_content(fields, model_name))
            except BaseException as e:
                self.log.error(f"{model_name}: {e}")
                pages_html = pages_html.replace("</HERE NAVIGATION>", "")
                pages_html = pages_html.replace(
                    "</HERE CONTENT>",
                    f"<h3><strong>404:</strong> This model has no field.</h3>\n",
                )
            os.makedirs(f"{self.output_folder}/{model_folder}", exist_ok=True)
            with open(f"{self.output_folder}/{model_folder}/index.html", "w", encoding="utf-8") as f:
                f.write(pages_html)

    def generate_nav_keys(self, keys, is_local=True, path=""):
        return [{
            "key": key,
            "id": key.replace(".", "_"),
            "path": f"{'#' + key.replace('.', '_') if is_local else path + '/' + key.replace('.', '_') + '/index.html'}"
        } for key in keys]
