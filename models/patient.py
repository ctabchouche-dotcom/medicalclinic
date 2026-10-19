# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import date


class ClinicPatient(models.Model):
    _name = 'clinic.patient'
    _description = 'Fiche Patient'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nom Complet', required=True, tracking=True)
    code = fields.Char(
        string='Numéro patient',
        copy=False,
        readonly=True,
        index=True,
        tracking=True,
        help="Numéro à ressaisir dans le logiciel de radiologie. Il relie l'image à cette fiche.",
    )
    gender = fields.Selection([
        ('male', 'Masculin'),
        ('female', 'Féminin'),
    ], string='Sexe', required=True, tracking=True)
    dob = fields.Date(string='Date de Naissance')
    age = fields.Integer(string='Âge', compute='_compute_age', store=True)
    phone = fields.Char(string='Téléphone', tracking=True)
    email = fields.Char(string='Email')
    blood_group = fields.Selection([
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ], string='Groupe Sanguin', tracking=True)
    medical_history = fields.Text(string='Antécédents Médicaux')
    active = fields.Boolean(string='Actif', default=True)
    radiology_ids = fields.One2many('clinic.radiology.request', 'patient_id', string='Radios')

    _code_unique = models.Constraint(
        'UNIQUE(code)',
        'Ce numéro patient existe déjà.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code('clinic.patient') or _('Nouveau')
        return super().create(vals_list)

    @api.model
    def _assign_missing_codes(self):
        for patient in self.search([('code', '=', False)]):
            patient.code = self.env['ir.sequence'].next_by_code('clinic.patient')

    @api.depends('dob')
    def _compute_age(self):
        today = date.today()
        for rec in self:
            if rec.dob:
                rec.age = today.year - rec.dob.year - ((today.month, today.day) < (rec.dob.month, rec.dob.day))
            else:
                rec.age = 0