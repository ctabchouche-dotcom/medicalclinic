# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ClinicRadiologyRequest(models.Model):
    _name = 'clinic.radiology.request'
    _description = 'Demande de radiographie'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Référence',
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _('Nouveau'),
    )
    patient_id = fields.Many2one(
        'clinic.patient', string='Patient', required=True, tracking=True,
    )
    patient_code = fields.Char(
        related='patient_id.code', string='Numéro patient', store=True, readonly=True,
    )
    doctor_id = fields.Many2one(
        'clinic.doctor', string='Médecin', required=True, tracking=True,
    )
    appointment_id = fields.Many2one('clinic.appointment', string='Rendez-vous')
    date = fields.Datetime(
        string='Date de la demande', default=fields.Datetime.now, required=True,
    )
    region = fields.Selection(
        [
            ('knee', 'Genou'),
            ('hip', 'Hanche'),
            ('spine', 'Rachis'),
            ('shoulder', 'Épaule'),
            ('ankle', 'Cheville'),
            ('wrist', 'Poignet'),
            ('hand', 'Main'),
            ('foot', 'Pied'),
            ('pelvis', 'Bassin'),
            ('elbow', 'Coude'),
            ('other', 'Autre'),
        ],
        string='Région',
        required=True,
        tracking=True,
    )
    side = fields.Selection(
        [
            ('left', 'Gauche'),
            ('right', 'Droit'),
            ('both', 'Les deux'),
            ('na', 'Sans côté'),
        ],
        string='Côté',
        required=True,
        default='na',
    )
    state = fields.Selection(
        [
            ('requested', 'Demandée'),
            ('image_received', 'Image reçue'),
            ('reported', 'Compte-rendu'),
        ],
        string='Statut',
        default='requested',
        tracking=True,
        group_expand=True,
    )
    study_url = fields.Char(
        string="Lien de l'image",
        help="Adresse de l'examen sur le serveur d'images du cabinet.",
    )
    study_uid = fields.Char(string='Identifiant DICOM')
    image_date = fields.Datetime(string="Image reçue le", readonly=True)
    report = fields.Text(string='Compte-rendu')

    _STATE_TRANSITIONS = {
        'requested': {'image_received'},
        'image_received': {'reported'},
        'reported': set(),
    }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code('clinic.radiology.request') or _('Nouveau')
        return super().create(vals_list)

    def action_open_image(self):
        self.ensure_one()
        if not self.study_url:
            raise UserError(_("Aucune image n'est liée à cette demande."))
        return {
            'type': 'ir.actions.act_url',
            'url': self.study_url,
            'target': 'new',
        }

    def action_mark_image_received(self):
        for rec in self:
            if not rec.study_url:
                raise UserError(_("Indiquez le lien de l'image avant de la marquer comme reçue."))
            rec._set_state('image_received')
            rec.image_date = fields.Datetime.now()
        return True

    def action_sign_report(self):
        for rec in self:
            if not (rec.report or '').strip():
                raise UserError(_("Écrivez le compte-rendu avant de le valider."))
            rec._set_state('reported')
        return True

    def _set_state(self, new_state):
        for rec in self:
            if new_state == rec.state:
                continue
            if new_state not in rec._STATE_TRANSITIONS.get(rec.state, ()):
                raise UserError(_("Ce changement de statut n'est pas autorisé."))
            rec.state = new_state

    @api.model
    def register_study(self, patient_code, study_url=None, study_uid=None):
        """Rattache une image arrivée du serveur DICOM à la demande ouverte."""
        code = (patient_code or '').strip()
        if not code:
            raise UserError(_("Le numéro patient est obligatoire."))
        patient = self.env['clinic.patient'].search([('code', '=', code)], limit=1)
        if not patient:
            raise UserError(_("Aucun patient avec le numéro %s.") % code)
        request = self.search([
            ('patient_id', '=', patient.id),
            ('state', '=', 'requested'),
        ], order='date, id', limit=1)
        if not request:
            raise UserError(_("Aucune radio en attente pour le patient %s.") % code)
        vals = {}
        if study_url:
            vals['study_url'] = study_url
        if study_uid:
            vals['study_uid'] = study_uid
        if vals:
            request.write(vals)
        if request.study_url:
            request.action_mark_image_received()
        return request
