# Copyright 2009-2020 Noviat
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Belgium - Multilingual Chart of Accounts (en/nl/fr)',
    'version': '12.0.1.0.2',
    'license': 'AGPL-3',
    'author': "Noviat",
    'website': 'http://www.noviat.com',
    'category': 'Localization',
    'depends': [
        'account_account_tag_code',
        'account_tax_code',
        'l10n_multilang',
        'l10n_account_translate_config',
        'base_vat',
        'base_iban',
        'account_move_line_tax_editable',
        'report_xlsx_helper',
        'web_tree_decoration_underline',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/res.country.state.csv',
        'data/account_chart_template_create.xml',
        'data/account_account_tag.xml',
        'data/account_tax_code_chart.xml',
        'data/account_account_template.xml',
        'data/account_chart_template_update.xml',
        'data/account_tax_template.xml',
        'data/account_fiscal_position_template.xml',
        'data/account_fiscal_position_tax_template.xml',
        'data/account_fiscal_position_account_template.xml',
        'data/be_legal_financial_report_chart.xml',
        'data/be_legal_financial_report_scheme.xml',
        'data/ir_sequence.xml',
        'views/menuitem.xml',
        'views/account_account_views.xml',
        'views/be_legal_financial_report_scheme_views.xml',
        'views/report_assets_common.xml',
        'views/l10n_be_layouts.xml',
        'views/report_l10nbevatdeclaration.xml',
        'views/report_l10nbevatintracom.xml',
        'views/report_l10nbevatlisting.xml',
        'views/report_l10nbelegalreport.xml',
        'views/res_partner_views.xml',
        'wizards/l10n_be_coa_multilang_config.xml',
        'wizards/l10n_be_update_be_reportscheme.xml',
        'wizards/l10n_be_vat_common.xml',
        'wizards/l10n_be_vat_declaration.xml',
        'wizards/l10n_be_vat_intracom.xml',
        'wizards/l10n_be_vat_listing.xml',
        'wizards/l10n_be_legal_report.xml',
        'data/account_chart_template_loading_data.xml',
    ],
    'installable': True,
}
