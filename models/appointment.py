from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ClinicAppointment(models.Model):
    _name = 'clinic.appointment'
    _description = 'Rendez-vous Médical'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'appointment_date desc'

    name = fields.Char(string='Référence', required=True, readonly=True, default=lambda self: _('Nouveau'))
    patient_id = fields.Many2one('clinic.patient', string='Patient', required=True, tracking=True)
    doctor_id = fields.Many2one('clinic.doctor', string='Médecin', required=True, tracking=True)
    appointment_date = fields.Datetime(string='Date du Rendez-vous', required=True, default=fields.Datetime.now, tracking=True)
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('confirmed', 'Confirmé'),
        ('done', 'Terminé'),
        ('cancel', 'Annulé'),
    ], string='Statut', default='draft', tracking=True, group_expand=True)
    notes = fields.Text(string='Notes / Motif de consultation')
    booked_online = fields.Boolean(
        string='Demandé sur le site',
        default=False,
        readonly=True,
        copy=False,
    )
    slot_id = fields.Many2one(
        'clinic.slot', string='Créneau', copy=False, readonly=True, ondelete='restrict',
    )
    consultation_notes = fields.Text(string='Compte rendu de consultation')
    prescription_ids = fields.One2many('clinic.prescription', 'appointment_id', string='Ordonnances')
    radiology_ids = fields.One2many('clinic.radiology.request', 'appointment_id', string='Radios')

    _STATE_TRANSITIONS = {
        'draft': {'confirmed', 'cancel'},
        'confirmed': {'done', 'cancel', 'draft'},
        'done': {'confirmed'},
        'cancel': {'draft'},
    }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code('clinic.appointment') or _('Nouveau')
        return super().create(vals_list)

    @api.model
    def book_public(self, slot_id, patient_name, phone, gender, email=None, notes=None):
        """Réserve un créneau confirmé par le médecin."""
        slot = self.env['clinic.slot'].browse(slot_id).exists()
        if not slot:
            raise UserError(_("Choisissez un créneau."))
        self.env.cr.execute(
            'SELECT id FROM clinic_slot WHERE id = %s FOR UPDATE',
            [slot.id],
        )
        slot.invalidate_recordset()
        if (
            slot.state != 'confirmed'
            or slot.appointment_id
            or slot.start <= fields.Datetime.now()
            or not slot.doctor_id.active
        ):
            raise UserError(_("Ce créneau n'est plus disponible."))
        name = (patient_name or '').strip()
        phone = (phone or '').strip()
        if len(name) < 2:
            raise UserError(_("Indiquez votre nom."))
        if len(phone) < 6:
            raise UserError(_("Indiquez un téléphone où la réception peut vous joindre."))
        if gender not in ('male', 'female'):
            raise UserError(_("Indiquez le sexe du patient."))
        patient = self.env['clinic.patient'].search([
            ('phone', '=', phone),
            ('name', '=ilike', name),
            ('active', '=', True),
        ], limit=1)
        if not patient:
            patient = self.env['clinic.patient'].create({
                'name': name[:128],
                'phone': phone[:32],
                'email': (email or '').strip()[:128] or False,
                'gender': gender,
            })
        reason = (notes or '').strip()[:4000]
        header = _("Demande envoyée depuis le site de la clinique.")
        appointment = self.create({
            'patient_id': patient.id,
            'doctor_id': slot.doctor_id.id,
            'appointment_date': slot.start,
            'notes': '%s\n%s' % (header, reason) if reason else header,
            'state': 'draft',
            'booked_online': True,
            'slot_id': slot.id,
        })
        slot.appointment_id = appointment
        return appointment

    def action_confirm(self):
        self.action_set_state('confirmed')

    def action_done(self):
        self.action_set_state('done')

    def action_cancel(self):
        self.action_set_state('cancel')

    def action_set_state(self, new_state):
        labels = dict(self._fields['state'].selection)
        if new_state not in labels:
            raise UserError(_("Statut inconnu."))
        for rec in self:
            if new_state == rec.state:
                continue
            if new_state not in rec._STATE_TRANSITIONS.get(rec.state, ()):
                raise UserError(_("Ce changement de statut n'est pas autorisé."))
            rec.write({'state': new_state})
            if new_state == 'cancel':
                self.env['clinic.slot'].search([
                    ('appointment_id', '=', rec.id),
                ]).write({'appointment_id': False})
        return True