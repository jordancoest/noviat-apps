# Copyright 2009-2021 Noviat.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import logging
import re
import time
from datetime import datetime

import xlrd

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class FixedAssetImport(models.TransientModel):
    _name = "fixed.asset.import"

    fa_data = fields.Binary(string="File", required=True)
    fa_fname = fields.Char(string="Filename")
    file_type = fields.Selection(
        selection="_selection_file_type", default=lambda self: self._default_file_type()
    )
    sheet = fields.Char(
        help="Specify the Excel sheet."
        "\nIf not specified the first sheet will be retrieved."
    )
    note = fields.Text("Log")
    compute_board = fields.Boolean(
        string="Compute Depreciation Board",
        help="Select this option if you want to compute "
        "the depreciation tables for the new created assets."
        "\nThis option may take a considerable amount of time "
        "when importing a large number of assets.",
    )

    @api.model
    def _selection_file_type(self):
        return [("xls", "xls"), ("xlsx", "xlsx")]

    @api.model
    def _default_file_type(self):
        return "xlsx"

    def _input_fields(self):
        res = {
            "reference": {"method": self._handle_reference, "field_type": "char"},
            "partner": {"method": self._handle_partner, "field_type": "char"},
            "asset profile": {"method": self._handle_profile, "field_type": "char"},
            "name": {"required": True},
            "purchase_value": {"required": True},
            "date_start": {"required": True},
            "profile_id": {"required": True},
        }
        return res

    def _get_orm_fields(self):
        fa_mod = self.env["account.asset"]
        orm_fields = fa_mod.fields_get()
        blacklist = models.MAGIC_COLUMNS + [fa_mod.CONCURRENCY_CHECK_FIELD]
        self._orm_fields = {
            f: orm_fields[f]
            for f in orm_fields
            if f not in blacklist and orm_fields[f]["store"]
        }

    def _process_header(self, header_fields):

        self._field_methods = self._input_fields()
        self._skip_fields = []

        # header fields after blank column are considered as comments
        column_cnt = 0
        for cnt in range(len(header_fields)):
            if header_fields[cnt] == "":
                column_cnt = cnt
                break
            elif cnt == len(header_fields) - 1:
                column_cnt = cnt + 1
                break
        header_fields = header_fields[:column_cnt]

        # check for duplicate header fields
        header_fields2 = []
        for hf in header_fields:
            if hf in header_fields2:
                raise UserError(
                    _(
                        "Duplicate header field '%s' found !"
                        "\nPlease correct the input file."
                    )
                    % hf
                )
            else:
                header_fields2.append(hf)

        for hf in header_fields:

            if hf in self._field_methods and self._field_methods[hf].get("method"):
                if not self._field_methods[hf].get("field_type"):
                    raise UserError(
                        _(
                            "Programming Error:"
                            "\nMissing formatting info for column '%s'." % hf
                        )
                    )
                continue

            if hf not in self._orm_fields and hf not in [
                self._orm_fields[f]["string"].lower() for f in self._orm_fields
            ]:
                _logger.error(
                    _("%s, undefined field '%s' found " "while importing assets"),
                    self._name,
                    hf,
                )
                self._skip_fields.append(hf)
                continue

            field_def = self._orm_fields.get(hf)
            if not field_def:
                for f in self._orm_fields:
                    if self._orm_fields[f]["string"].lower() == hf:
                        orm_field = f
                        field_def = self._orm_fields.get(f)
                        break
            else:
                orm_field = hf
            field_type = field_def["type"]

            try:
                ft = field_type == "text" and "char" or field_type
                self._field_methods[hf] = {
                    "method": getattr(self, "_handle_orm_%s" % ft),
                    "orm_field": orm_field,
                    "field_type": field_type,
                }
            except AttributeError:
                _logger.error(
                    _(
                        "%s, field '%s', "
                        "the import of ORM fields of type '%s' "
                        "is not supported"
                    ),
                    self._name,
                    hf,
                    field_type,
                )
                self._skip_fields.append(hf)

        return header_fields

    def _log_line_error(self, line, msg):
        if not line.get("log_line_error"):
            data = " | ".join(["%s" % line[hf] for hf in self._header_fields])
            self._err_log += (
                _("Error when processing line '%s'") % data + ":\n" + msg + "\n\n"
            )
            # Add flag to avoid reporting two times the same line.
            # This could happen for errors detected by
            # _read_xls as well as _proces_%
            line["log_line_error"] = True

    def _handle_orm_char(self, field, line, fa_vals, orm_field=False):
        orm_field = orm_field or field
        fa_vals[orm_field] = line[field]

    def _handle_orm_date(self, field, line, fa_vals, orm_field=False):
        orm_field = orm_field or field
        fa_vals[orm_field] = line[field]

    def _handle_orm_selection(self, field, line, fa_vals, orm_field=False):
        orm_field = orm_field or field
        fa_vals[orm_field] = line[field]

    def _handle_orm_integer(self, field, line, fa_vals, orm_field=False):
        orm_field = orm_field or field
        val = line[field]
        if isinstance(val, str):
            val = str2int(val)
        if val and not isinstance(val, int):
            msg = _("Incorrect value '%s' " "for field '%s' of type Integer !") % (
                line[field],
                field,
            )
            self._log_line_error(line, msg)
        else:
            fa_vals[orm_field] = val

    def _handle_orm_float(self, field, line, fa_vals, orm_field=False):
        val = line[field]
        if isinstance(val, str):
            val = str2float(val)
        if not isinstance(val, float):
            msg = _("Incorrect value '%s' " "for field '%s' of type Numeric !") % (
                line[field],
                field,
            )
            self._log_line_error(line, msg)
        else:
            fa_vals[orm_field] = val

    def _handle_orm_boolean(self, field, line, fa_vals, orm_field=False):
        orm_field = orm_field or field
        if not fa_vals.get(orm_field):
            val = line[field]
            if isinstance(val, str):
                val = val.strip().capitalize()
                if val in ["", "0", "False"]:
                    val = False
                elif val in ["1", "True"]:
                    val = True
                if isinstance(val, str):
                    msg = _(
                        "Incorrect value '%s' " "for field '%s' of type Boolean !"
                    ) % (line[field], field)
                    self._log_line_error(line, msg)
            fa_vals[orm_field] = val

    def _handle_orm_many2one(self, field, line, fa_vals, orm_field=False):
        orm_field = orm_field or field
        val = line[field]
        if isinstance(val, str):
            val = str2int(val)
        if val and not isinstance(val, int):
            msg = _(
                "Incorrect value '%s' "
                "for field '%s' of type Many2One !"
                "\nYou should specify the database key "
                "or contact your IT department "
                "to add support for this field."
            ) % (line[field], field)
            self._log_line_error(line, msg)
        else:
            fa_vals[orm_field] = val

    def _handle_reference(self, field, line, fa_vals):
        code = line[field]
        if code:
            dups = self.env["account.asset"].search([("code", "=", code)])
            if dups:
                msg = _("Duplicate Asset with reference '%s' found !") % code
                self._log_line_error(line, msg)
                return
            fa_vals["code"] = code

    def _handle_partner(self, field, line, fa_vals):
        if not fa_vals.get("partner_id"):
            input_val = line[field]
            part_mod = self.env["res.partner"]
            dom = ["|", ("parent_id", "=", False), ("is_company", "=", True)]
            dom_ref = dom + [("ref", "=", input_val)]
            partners = part_mod.search(dom_ref)
            if not partners:
                dom_name = dom + [("name", "=", input_val)]
                partners = part_mod.search(dom_name)
            if not partners:
                msg = _("Partner '%s' not found !") % input_val
                self._log_line_error(line, msg)
                return
            elif len(partners) > 1:
                msg = (
                    _("Multiple partners with Reference " "or Name '%s' found !")
                    % input_val
                )
                self._log_line_error(line, msg)
                return
            else:
                partner = partners[0]
                fa_vals["partner_id"] = partner.id

    def _handle_profile(self, field, line, fa_vals):
        if not fa_vals.get("profile_id"):
            input_val = line[field]
            profile = self.env["account.asset.profile"].search(
                [("name", "=", input_val)]
            )
            if not profile:
                msg = _("Profile '%s' not found !") % input_val
                self._log_line_error(line, msg)
                return
            elif len(profile) > 1:
                msg = (
                    _(
                        "Multiple profiles with Internal Reference "
                        "or Name '%s' found !"
                    )
                    % input_val
                )
                self._log_line_error(line, msg)
                return
            else:
                fa_vals["profile_id"] = profile.id

    def _process_fa_vals(self, line, fa_vals):
        """
        Use this method if you want to check/modify the
        input values dict before calling the create() method
        """
        all_fields = self._field_methods
        required_fields = [x for x in all_fields if all_fields[x].get("required")]
        for rf in required_fields:
            if rf not in fa_vals:
                msg = (
                    _(
                        "The '%s' field is a required field "
                        "that must be correctly set."
                    )
                    % rf
                )
                self._log_line_error(line, msg)

    def _read_xls(self, data):  # noqa: C901
        wb = xlrd.open_workbook(file_contents=data)
        if self.sheet:
            try:
                sheet = wb.sheet_by_name(self.sheet)
            except xlrd.XLRDError as e:
                self.warning = _(
                    "Error while reading Excel sheet: <br>{}".format(str(e))
                )
                return
        else:
            sheet = wb.sheet_by_index(0)
        lines = []
        header = False
        for ri in range(sheet.nrows):
            err_msg = ""
            line = {}
            ln = sheet.row_values(ri)
            if all([x == "" for x in ln]):
                continue
            if ln[0] and isinstance(ln[0], str) and ln[0][0] == "#":
                continue
            if not header:
                header = [x.lower() for x in ln]
                self._header_fields = self._process_header(header)
            else:
                for ci, hf in enumerate(self._header_fields):
                    line[hf] = False
                    val = False
                    cell = sheet.cell(ri, ci)
                    if hf in self._skip_fields:
                        continue
                    if cell.ctype in [xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK]:
                        continue
                    if cell.ctype == xlrd.XL_CELL_ERROR:
                        if err_msg:
                            err_msg += "\n"
                        err_msg += _("Incorrect value '%s' " "for field '%s' !") % (
                            cell.value,
                            hf,
                        )
                        continue

                    fmt = self._field_methods[hf]["field_type"]

                    if fmt == "char":
                        if cell.ctype == xlrd.XL_CELL_TEXT:
                            val = cell.value
                        elif cell.ctype == xlrd.XL_CELL_NUMBER:
                            is_int = cell.value % 1 == 0.0
                            if is_int:
                                val = str(int(cell.value))
                            else:
                                val = str(cell.value)
                        else:
                            val = str(cell.value)

                    elif fmt == "float":
                        if cell.ctype == xlrd.XL_CELL_TEXT:
                            amount = cell.value
                            val = str2float(amount)
                        else:
                            val = cell.value

                    elif fmt in ["integer", "many2one"]:
                        val = cell.value
                        if val:
                            is_int = val % 1 == 0.0
                            if is_int:
                                val = int(val)
                            else:
                                if err_msg:
                                    err_msg += "\n"
                                err_msg += _(
                                    "Incorrect value '%s' "
                                    "for field '%s' of type %s !"
                                ) % (cell.value, hf, fmt.capitalize())

                    elif fmt == "boolean":
                        if cell.ctype == xlrd.XL_CELL_TEXT:
                            val = cell.value.capitalize().strip()
                            if val in ["", "0", "False"]:
                                val = False
                            elif val in ["1", "True"]:
                                val = True
                        else:
                            is_int = cell.value % 1 == 0.0
                            if is_int:
                                val = val == 1 and True or False
                            else:
                                val = None
                        if val is None:
                            if err_msg:
                                err_msg += "\n"
                            err_msg += _(
                                "Incorrect value '%s' "
                                "for field '%s' of type Boolean !"
                            ) % (cell.value, hf)

                    elif fmt == "date":
                        if cell.ctype == xlrd.XL_CELL_TEXT:
                            if cell.value:
                                val = str2date(cell.value)
                                if not val:
                                    if err_msg:
                                        err_msg += "\n"
                                    err_msg += _(
                                        "Incorrect value '%s' "
                                        "for field '%s' of type Date !"
                                        " should be YYYY-MM-DD"
                                    ) % (cell.value, hf)
                        elif cell.ctype in [xlrd.XL_CELL_NUMBER, xlrd.XL_CELL_DATE]:
                            val = xlrd.xldate.xldate_as_tuple(cell.value, wb.datemode)
                            val = datetime(*val).strftime("%Y-%m-%d")
                        elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                            if err_msg:
                                err_msg += "\n"
                            err_msg += _(
                                "Incorrect value '%s' " "for field '%s' of type Date !"
                            ) % (cell.value, hf)

                    else:
                        _logger.error(
                            "%s, field '%s', Unsupported format '%s'",
                            self._name,
                            hf,
                            fmt,
                        )
                        raise NotImplementedError

                    if val:
                        line[hf] = val

                if err_msg:
                    self._log_line_error(line, err_msg)

                if line:
                    lines.append(line)

        return lines

    def fa_import(self):

        time_start = time.time()
        self._err_log = ""
        self._get_orm_fields()
        data = base64.decodestring(self.fa_data)
        lines = self._read_xls(data)

        fa_vals_list = []
        for line in lines:

            fa_vals = {}

            # step 2: process input fields
            for i, hf in enumerate(self._header_fields):
                if i == 0 and line[hf] and line[hf][0] == "#":
                    # lines starting with # are considered as comment lines
                    break
                if hf in self._skip_fields:
                    continue
                if line[hf] == "":
                    continue

                if self._field_methods[hf].get("orm_field"):
                    self._field_methods[hf]["method"](
                        hf,
                        line,
                        fa_vals,
                        orm_field=self._field_methods[hf]["orm_field"],
                    )
                else:
                    self._field_methods[hf]["method"](hf, line, fa_vals)

            if fa_vals:
                self._process_fa_vals(line, fa_vals)
                fa_vals_list.append(fa_vals)

        module = __name__.split("addons.")[1].split(".")[0]
        result_view = self.env.ref("{}.{}_view_form_result".format(module, self._table))

        ctx = self.env.context.copy()
        if self._err_log:
            self.note = self._err_log
        else:
            new_assets = self.env["account.asset"]
            for fa_vals in fa_vals_list:
                fa = self.env["account.asset"].create(fa_vals)
                new_assets += fa
            if self.compute_board:
                new_assets.compute_depreciation_board()
            import_time = time.time() - time_start
            self.note = "%s assets have been created." % len(new_assets)
            ctx["new_asset_ids"] = new_assets.ids
            _logger.warn(
                "%s assets have been created, " "import time = %.3f seconds.",
                len(new_assets),
                import_time,
            )
        return {
            "name": _("Import result"),
            "res_id": self.id,
            "view_type": "form",
            "view_mode": "form",
            "res_model": self._name,
            "view_id": result_view.id,
            "target": "new",
            "type": "ir.actions.act_window",
            "context": ctx,
        }

    def view_assets(self):
        self.ensure_one()
        domain = [("id", "in", self._context.get("new_asset_ids", []))]
        return {
            "name": _("Imported Assets"),
            "view_type": "form",
            "view_mode": "tree,form",
            "res_model": "account.asset",
            "view_id": False,
            "domain": domain,
            "type": "ir.actions.act_window",
        }


def str2float(val):
    pattern = re.compile("[0-9]")
    dot_comma = pattern.sub("", val)
    if dot_comma and dot_comma[-1] in [".", ","]:
        decimal_separator = dot_comma[-1]
    else:
        decimal_separator = False
    if decimal_separator == ".":
        val = val.replace(",", "")
    else:
        val = val.replace(".", "").replace(",", ".")
    try:
        return float(val)
    except Exception:
        return None


def str2int(amount):
    pattern = re.compile("[0-9]")
    dot_comma = pattern.sub("", amount)
    if dot_comma and dot_comma[-1] in [".", ","]:
        decimal_separator = dot_comma[-1]
    else:
        decimal_separator = False
    try:
        if decimal_separator == ".":
            return int(amount.replace(",", ""))
        else:
            return int(amount.replace(".", "").replace(",", "."))
    except Exception:
        return False


def str2date(date_str):
    try:
        return time.strftime("%Y-%m-%d", time.strptime(date_str, "%Y-%m-%d"))
    except Exception:
        return False
