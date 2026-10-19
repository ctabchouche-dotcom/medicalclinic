# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ClinicPrescription(models.Model):
    _name = 'clinic.prescription'
    _description = 'Ordonnance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Référence', required=True, readonly=True, copy=False,
        default=lambda self: _('Nouveau'),
    )
    patient_id = fields.Many2one('clinic.patient', string='Patient', required=True, tracking=True)
    doctor_id = fields.Many2one('clinic.doctor', string='Médecin', required=True, tracking=True)
    appointment_id = fields.Many2one('clinic.appointment', string='Consultation')
    date = fields.Datetime(string='Date', default=fields.Datetime.now, required=True)
    notes = fields.Text(string='Conseils')
    line_ids = fields.One2many('clinic.prescription.line', 'prescription_id', string='Médicaments', copy=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code('clinic.prescription') or _('Nouveau')
        return super().create(vals_list)

    def _patient_label(self):
        self.ensure_one()
        patient = self.patient_id
        bits = [patient.name or '']
        if patient.age:
            bits.append('%s ans' % patient.age)
        return ' — '.join(bit for bit in bits if bit)

    @api.model
    def _configure_prescription_mail_template(self):
        template = self.env.ref(
            'medicalclinic.email_template_prescription', raise_if_not_found=False,
        )
        report = self.env.ref(
            'medicalclinic.action_report_clinic_prescription', raise_if_not_found=False,
        )
        if not template or not report:
            return
        sender = self.env['clinic.lab.request']._results_email_from()
        template.sudo().write({
            'subject': "Votre ordonnance - {{ object.name }}",
            'email_from': sender or '{{ user.email_formatted }}',
            'email_to': '{{ object.patient_id.email }}',
            'use_default_to': False,
            'body_html': """
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333333;">
    <p>Bonjour <strong t-out="object.patient_id.name or ''">Patient</strong>,</p>
    <p>Veuillez trouver votre ordonnance (Réf : <strong t-out="object.name or ''">ORD/001</strong>), prescrite par le <strong>Dr. <t t-out="object.doctor_id.name or ''">Médecin</t></strong>.</p>
    <p>Le PDF joint indique les médicaments, la posologie et la durée du traitement.</p>
    <p>Cordialement,<br/><strong>La clinique</strong></p>
</div>
""",
            'report_template_ids': [(4, report.id)],
        })

    def _send_prescription_email(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Ajoutez au moins un médicament avant d'envoyer l'ordonnance."))
        email = (self.patient_id.email or '').strip()
        if not email:
            raise UserError(_("Ce patient n'a pas d'adresse e-mail."))
        template = self.env.ref(
            'medicalclinic.email_template_prescription', raise_if_not_found=False,
        )
        if not template:
            raise UserError(_("Le modèle d'e-mail de l'ordonnance est introuvable."))
        sender = self.env['clinic.lab.request']._results_email_from()
        if not sender:
            raise UserError(_("Aucun serveur d'envoi n'est configuré."))
        self._configure_prescription_mail_template()
        try:
            mail_id = template.sudo().send_mail(
                self.id,
                force_send=True,
                raise_exception=True,
                email_values={'email_to': email, 'email_from': sender},
            )
        except UserError:
            raise
        except Exception as err:
            _logger.exception("Envoi de l'ordonnance impossible pour %s", self.name)
            raise UserError(_("L'e-mail n'a pas pu être envoyé : %s") % err) from err
        mail = self.env['mail.mail'].sudo().browse(mail_id)
        if mail.state == 'exception':
            reason = (mail.failure_reason or _("connexion refusée par le serveur mail")).strip()
            raise UserError(_("L'e-mail n'a pas pu être envoyé : %s") % reason)
        return True


class ClinicPrescriptionLine(models.Model):
    _name = 'clinic.prescription.line'
    _description = "Ligne d'ordonnance"
    _order = 'sequence, id'

    prescription_id = fields.Many2one(
        'clinic.prescription', string='Ordonnance', required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10)
    medication_id = fields.Many2one('clinic.medication', string='Médicament', required=True)
    dosage = fields.Char(string='Posologie', required=True, help='Ex. : 1 comprimé 3 fois par jour.')
    duration = fields.Char(string='Durée', help='Ex. : 7 jours.')
    quantity = fields.Char(string='Quantité', help='Ex. : 1 boîte.')
    instructions = fields.Char(string='Précisions')
