# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ClinicMedication(models.Model):
    _name = 'clinic.medication'
    _description = 'Médicament'
    _order = 'drug_class, name, strength'
    _rec_name = 'name'

    name = fields.Char(string='Nom', required=True, index=True)
    dci = fields.Char(string='DCI', index=True, help='Dénomination commune internationale.')
    strength = fields.Char(string='Dosage')
    form = fields.Selection([
        ('tablet', 'Comprimé'),
        ('capsule', 'Gélule'),
        ('syrup', 'Sirop'),
        ('sachet', 'Sachet'),
        ('injection', 'Injectable'),
        ('cream', 'Pommade / crème'),
        ('drops', 'Gouttes'),
        ('spray', 'Spray'),
        ('suppository', 'Suppositoire'),
    ], string='Forme', required=True, default='tablet')
    route = fields.Selection([
        ('oral', 'Orale'),
        ('local', 'Locale'),
        ('injection', 'Injectable'),
        ('inhaled', 'Inhalée'),
        ('ophthalmic', 'Ophtalmique'),
    ], string='Voie', required=True, default='oral')
    drug_class = fields.Selection([
        ('antibiotic', 'Antibiotique'),
        ('anti_inflammatory', 'Anti-inflammatoire'),
        ('analgesic', 'Antalgique / antipyrétique'),
        ('antihypertensive', 'Antihypertenseur'),
        ('antidiabetic', 'Antidiabétique'),
        ('gastric', 'Digestif / gastrique'),
        ('antihistamine', 'Antihistaminique'),
        ('corticosteroid', 'Corticoïde'),
        ('vitamin', 'Vitamine / supplément'),
        ('other', 'Autre'),
    ], string='Classe', required=True, default='other', index=True)
    search_text = fields.Char(compute='_compute_search_text', store=True, index=True)
    active = fields.Boolean(default=True)

    @api.depends('name', 'dci', 'strength', 'form', 'drug_class')
    def _compute_search_text(self):
        forms = dict(self._fields['form'].selection)
        classes = dict(self._fields['drug_class'].selection)
        for rec in self:
            rec.search_text = ' '.join(part for part in (
                rec.name,
                rec.dci,
                rec.strength,
                forms.get(rec.form),
                classes.get(rec.drug_class),
            ) if part)

    @api.depends('name', 'dci', 'strength', 'form', 'drug_class')
    def _compute_display_name(self):
        forms = dict(self._fields['form'].selection)
        classes = dict(self._fields['drug_class'].selection)
        for rec in self:
            title = rec.name or ''
            if rec.strength:
                title = '%s %s' % (title, rec.strength)
            rec.display_name = '%s — %s (%s)' % (
                title,
                forms.get(rec.form, ''),
                classes.get(rec.drug_class, ''),
            )

    @api.model
    def _search_display_name(self, operator, value):
        if value and operator in ('ilike', 'like', '=ilike', '=like'):
            return ['|', '|', ('name', operator, value), ('dci', operator, value), ('search_text', operator, value)]
        return super()._search_display_name(operator, value)
