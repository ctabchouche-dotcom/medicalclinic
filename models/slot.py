# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

SLOT_MINUTES = 30


class ClinicSlot(models.Model):
    _name = 'clinic.slot'
    _description = 'Créneau de consultation'
    _inherit = ['mail.thread']
    _order = 'start, id'

    doctor_id = fields.Many2one(
        'clinic.doctor', string='Médecin', required=True, ondelete='restrict', tracking=True,
    )
    start = fields.Datetime(string='Début', required=True, tracking=True)
    stop = fields.Datetime(string='Fin', required=True, tracking=True)
    state = fields.Selection(
        [
            ('draft', 'Brouillon'),
            ('sent', 'Chez le médecin'),
            ('confirmed', 'Confirmé'),
        ],
        string='Statut',
        default='draft',
        required=True,
        tracking=True,
    )
    appointment_id = fields.Many2one(
        'clinic.appointment', string='Rendez-vous', copy=False, readonly=True, ondelete='set null',
    )

    _stop_after_start = models.Constraint(
        'CHECK(stop > start)',
        "L'heure de fin doit être après l'heure de début.",
    )

    def action_send(self):
        now = fields.Datetime.now()
        for slot in self:
            if slot.state != 'draft':
                raise UserError(_("Seuls les créneaux en brouillon peuvent être envoyés."))
            if slot.start <= now:
                raise UserError(_("Un créneau passé ne peut pas être envoyé au médecin."))
        self.write({'state': 'sent'})
        return True

    def action_confirm(self):
        for slot in self:
            if slot.state != 'sent':
                raise UserError(_("Le médecin confirme un créneau qui lui a été envoyé."))
            if slot.appointment_id:
                raise UserError(_("Ce créneau est déjà pris."))
        self.write({'state': 'confirmed'})
        return True

    def update_times(self, start, stop):
        self.ensure_one()
        if self.appointment_id:
            raise UserError(_("Ce créneau est déjà réservé."))
        if self.state == 'draft':
            raise UserError(_("Le médecin modifie un créneau qui lui a été envoyé."))
        if not start or not stop or stop <= start:
            raise UserError(_("L'heure de fin doit être après l'heure de début."))
        self.write({'start': start, 'stop': stop})
        return True

    @api.model
    def apply_week(self, doctor, week_start, week_end, wanted_starts):
        """Replace one doctor's draft slots for a week.

        ``wanted_starts`` lists the checked hours as naive UTC datetimes.
        Each new slot lasts 30 minutes. Sent, confirmed and booked slots stay.
        Hours that have already started are ignored.
        """
        if not doctor or not doctor.active:
            raise UserError(_("Choisissez un médecin."))
        if not week_start or not week_end or week_end <= week_start:
            raise UserError(_("Semaine invalide."))
        wanted = {start.replace(microsecond=0) for start in wanted_starts if start}
        existing = self.search([
            ('doctor_id', '=', doctor.id),
            ('start', '>=', week_start),
            ('start', '<', week_end),
        ])
        kept = set()
        removed = 0
        for slot in existing:
            start = slot.start.replace(microsecond=0)
            minutes = int((slot.stop - slot.start).total_seconds() // 60)
            if minutes != SLOT_MINUTES:
                continue
            if slot.state != 'draft' or slot.appointment_id or start in wanted:
                kept.add(start)
                continue
            slot.unlink()
            removed += 1
        now = fields.Datetime.now()
        created = 0
        skipped_past = 0
        for start in sorted(wanted - kept):
            if start < week_start or start >= week_end:
                continue
            if start <= now:
                skipped_past += 1
                continue
            self.create({
                'doctor_id': doctor.id,
                'start': start,
                'stop': start + timedelta(minutes=SLOT_MINUTES),
            })
            created += 1
        return {'created': created, 'removed': removed, 'skipped_past': skipped_past}

    @api.model
    def available_for(self, doctor):
        return self.search([
            ('doctor_id', '=', doctor.id),
            ('state', '=', 'confirmed'),
            ('appointment_id', '=', False),
            ('start', '>', fields.Datetime.now()),
        ])
