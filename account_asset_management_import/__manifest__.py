# Copyright 2009-2021 Noviat.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Fixed Assets import",
    "version": "13.0.1.0.0",
    "license": "AGPL-3",
    "author": "Noviat",
    "website": "http://www.noviat.com",
    "category": "Accounting & Finance",
    "depends": ["account_asset_management"],
    "external_dependencies": {"python": ["xlrd"]},
    "data": ["wizards/fixed_asset_import_views.xml"],
    "installable": True,
}
