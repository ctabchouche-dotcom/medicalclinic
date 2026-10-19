# -*- coding: utf-8 -*-
from odoo import models, fields


class ClinicDoctor(models.Model):
    _name = 'clinic.doctor'
    _description = 'Médecin / Spécialiste'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nom du Médecin', required=True, tracking=True)
    specialty = fields.Char(string='Spécialité', required=True, tracking=True)
    phone = fields.Char(string='Téléphone')
    email = fields.Char(string='Email')
    consultation_fee = fields.Float(string='Tarif Consultation', required=True)
    user_id = fields.Many2one('res.users', string='Compte Utilisateur Odoo')
    active = fields.Boolean(string='Actif', default=True)