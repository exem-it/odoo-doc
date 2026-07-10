import hashlib
import os

from Log import Log


class GenerateSql:
    """
    Generates a PostgreSQL DDL (schema.sql) describing the data architecture
    of the Odoo models, in parallel with the HTML documentation.

    It is fed with the exact same `fields_get` data used to build the HTML
    pages (via `add_model`), so no additional RPC call is made. Once every
    model has been added, `write()` emits a single, psql-runnable script:

      1. DROP TABLE IF EXISTS ... CASCADE  (so the script is re-runnable)
      2. CREATE TABLE per model            (stored scalar + many2one columns)
      3. CREATE TABLE per many2many relation (join) table
      4. ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY

    Foreign keys are emitted as separate ALTER TABLE statements after every
    table so creation order never matters, circular references are fine, and
    schema/diagram tools (DataGrip, DBeaver, SchemaSpy, ...) read the model
    cleanly. Load it with:  psql -d <db> -f schema.sql
    """

    # Odoo field type -> PostgreSQL column type.
    # one2many is never stored (inverse side), many2many is handled as a join
    # table; both are therefore absent from this map.
    TYPE_MAP = {
        "char": "varchar",
        "text": "text",
        "html": "text",
        "selection": "varchar",
        "reference": "varchar",
        "integer": "integer",
        "float": "numeric",
        "monetary": "numeric",
        "boolean": "boolean",
        "date": "date",
        "datetime": "timestamp",
        "binary": "bytea",
        "json": "jsonb",
        "properties": "jsonb",
        "properties_definition": "jsonb",
        "many2one": "integer",
    }

    def __init__(self, main_folder):
        self.log = Log("GenerateSql")
        self.output_file = f"{main_folder}/schema.sql"

        # table_name -> list of column dicts:
        #   {name, definition, comment, ref, on_delete}
        # `definition` is the quoted name + type + NULL constraint (no FK);
        # `ref` is the many2one target table (or None), resolved to a foreign
        # key once every table is known.
        self.tables = {}
        # every generated table name, to validate FK targets exist
        self.model_tables = set()
        # count of many2one relations whose target has no table
        self.skipped_fks = 0
        # join table name -> dict(cols=[(col, target_table), ...], via=set(labels))
        self.m2m_tables = {}

    @staticmethod
    def _table_name(model_name):
        return model_name.replace(".", "_")

    def sql_type(self, ttype):
        return self.TYPE_MAP.get(ttype, "varchar")

    @staticmethod
    def _quote(identifier):
        # Double-quote every identifier so reserved words (e.g. a column named
        # "delete") stay valid.
        return '"' + identifier.replace('"', '""') + '"'

    # PostgreSQL truncates identifiers to 63 bytes, which can collide long
    # derived names (join tables, FK constraints) into duplicates. Shorten
    # deterministically with a hash suffix so every name stays unique.
    _MAX_IDENTIFIER = 63

    @classmethod
    def _short(cls, name):
        if len(name.encode("utf-8")) <= cls._MAX_IDENTIFIER:
            return name
        digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
        return name[:cls._MAX_IDENTIFIER - 9] + "_" + digest

    def add_model(self, model_name, fields):
        table = self._table_name(model_name)
        self.model_tables.add(table)

        columns = [{
            "name": "id",
            "definition": f'{self._quote("id")} integer NOT NULL PRIMARY KEY',
            "comment": "Odoo primary key (serial in a real DB)",
            "ref": None,
            "on_delete": None,
        }]

        for name in sorted(fields.keys()):
            field = fields[name]
            ttype = field.get("type")

            if name == "id" or ttype == "one2many":
                continue

            if ttype == "many2many":
                self._add_m2m(table, model_name, name, field)
                continue

            col_type = self.sql_type(ttype)
            constraints = " NOT NULL" if field.get("required") else ""

            ref_target = None
            if ttype == "many2one" and field.get("relation"):
                ref_target = self._table_name(field["relation"])

            label = field.get("string") or ""
            columns.append({
                "name": name,
                "definition": f"{self._quote(name)} {col_type}{constraints}",
                "comment": f"{label} [{ttype}]".strip(),
                "ref": ref_target,
                "on_delete": "SET NULL",
            })

        self.tables[table] = columns

    def _add_m2m(self, table, model_name, field_name, field):
        relation = field.get("relation")
        if not relation:
            return
        target = self._table_name(relation)

        # Deterministic join-table name independent of which side declares the
        # field, so both-sided definitions collapse to a single table.
        a, b = sorted([table, target])
        rel_name = self._short(f"{a}_{b}_rel")

        if a == b:
            # Self-referential many2many: both columns point at the same table,
            # so the names must be disambiguated to avoid a duplicate column.
            cols = [(self._short(f"{a}_id"), a),
                    (self._short(f"{b}_target_id"), b)]
        else:
            cols = [(self._short(f"{a}_id"), a),
                    (self._short(f"{b}_id"), b)]

        if rel_name not in self.m2m_tables:
            self.m2m_tables[rel_name] = {
                "cols": cols,
                "via": set(),
            }
        self.m2m_tables[rel_name]["via"].add(f"{model_name}.{field_name}")

    def _foreign_keys(self):
        """
        All foreign keys (many2one columns + many2many join columns) whose
        target is a real table, as {table, column, target, on_delete} dicts.
        Sets self.skipped_fks (many2one targets without a table).
        """
        fks = []
        skipped = 0
        for table in sorted(self.tables.keys()):
            for col in self.tables[table]:
                ref = col["ref"]
                if not ref:
                    continue
                if ref in self.model_tables:
                    fks.append({
                        "table": table,
                        "column": col["name"],
                        "target": ref,
                        "on_delete": col["on_delete"],
                    })
                else:
                    skipped += 1
        for rel_name in sorted(self.m2m_tables.keys()):
            for col, target in self.m2m_tables[rel_name]["cols"]:
                if target in self.model_tables:
                    fks.append({
                        "table": rel_name,
                        "column": col,
                        "target": target,
                        "on_delete": "CASCADE",
                    })
        self.skipped_fks = skipped
        return fks

    def _render_drops(self, out):
        out.append("-- =====================================================")
        out.append("-- Drop existing objects (makes the script re-runnable)")
        out.append("-- =====================================================\n")
        names = sorted(self.tables.keys()) + sorted(self.m2m_tables.keys())
        for name in names:
            out.append(f"DROP TABLE IF EXISTS {self._quote(name)} CASCADE;")
        out.append("")

    def _render_tables(self, out):
        out.append("-- =====================================================")
        out.append("-- Tables (one per Odoo model)")
        out.append("-- =====================================================\n")
        for table in sorted(self.tables.keys()):
            columns = self.tables[table]
            out.append(f"CREATE TABLE {self._quote(table)} (")
            lines = []
            for i, col in enumerate(columns):
                separator = "," if i < len(columns) - 1 else ""
                suffix = f"  -- {col['comment']}" if col["comment"] else ""
                lines.append(f"    {col['definition']}{separator}{suffix}")
            out.append("\n".join(lines))
            out.append(");\n")

    def _render_m2m_tables(self, out):
        if not self.m2m_tables:
            return
        out.append("-- =====================================================")
        out.append("-- Many2many relation (join) tables")
        out.append("-- =====================================================\n")
        for rel_name in sorted(self.m2m_tables.keys()):
            info = self.m2m_tables[rel_name]
            (col1, _), (col2, _) = info["cols"]
            via = ", ".join(sorted(info["via"]))
            out.append(f"-- via {via}")
            out.append(f"CREATE TABLE {self._quote(rel_name)} (")
            out.append(f"    {self._quote(col1)} integer NOT NULL,")
            out.append(f"    {self._quote(col2)} integer NOT NULL,")
            out.append(
                f"    PRIMARY KEY ({self._quote(col1)}, {self._quote(col2)})"
            )
            out.append(");\n")

    def _render_foreign_keys(self, out, fks):
        out.append("-- =====================================================")
        out.append("-- Foreign keys (declared after all tables)")
        out.append("-- =====================================================\n")
        for fk in fks:
            constraint = self._short(f'{fk["table"]}_{fk["column"]}_fkey')
            out.append(
                f'ALTER TABLE {self._quote(fk["table"])}\n'
                f'    ADD CONSTRAINT {self._quote(constraint)}\n'
                f'    FOREIGN KEY ({self._quote(fk["column"])})\n'
                f'    REFERENCES {self._quote(fk["target"])} ({self._quote("id")})\n'
                f'    ON DELETE {fk["on_delete"]};'
            )
        out.append("")

    def render(self):
        """Build the full PostgreSQL DDL string."""
        fks = self._foreign_keys()  # sets self.skipped_fks

        body = []
        self._render_drops(body)
        self._render_tables(body)
        self._render_m2m_tables(body)
        self._render_foreign_keys(body, fks)

        header = [
            "-- Odoo data architecture (auto-generated PostgreSQL DDL)",
            "-- Generated from ir.model / fields_get, in parallel with the HTML docs.",
            "-- Load with:  psql -d <database> -f schema.sql",
            f"-- Models: {len(self.model_tables)}, "
            f"join tables: {len(self.m2m_tables)}, "
            f"foreign keys: {len(fks)}, "
            f"many2one relations skipped (no target table): {self.skipped_fks}.\n",
            "BEGIN;\n",
        ]
        return "\n".join(header + body + ["COMMIT;"])

    def write(self):
        ddl = self.render()
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write(ddl)
        self.log.info(
            f"schema.sql written: {len(self.tables)} tables, "
            f"{len(self.m2m_tables)} join tables "
            f"({self.skipped_fks} many2one FKs skipped) to {self.output_file}"
        )
