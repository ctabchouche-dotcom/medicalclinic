# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

import pytz

from odoo import fields, http, _
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

WEEKDAYS = ('lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche')


def clinic_tz_name():
    user = request.env.user
    company_tz = request.env.company.sudo().partner_id.tz
    return user.tz or company_tz or 'Africa/Algiers'


def clinic_tz():
    return pytz.timezone(clinic_tz_name())


def local_to_utc(day, hour):
    raw_hour = (hour or '').strip()[:5]
    try:
        naive = datetime.strptime('%sT%s' % ((day or '').strip(), raw_hour), '%Y-%m-%dT%H:%M')
    except ValueError as exc:
        raise UserError(_("Date ou heure invalide.")) from exc
    return clinic_tz().localize(naive).astimezone(pytz.UTC).replace(tzinfo=None)


def utc_to_local(value):
    if not value:
        return None
    return pytz.UTC.localize(value).astimezone(clinic_tz())


def week_bounds(week_start):
    start = datetime.strptime(week_start, '%Y-%m-%d')
    start = start - timedelta(days=start.weekday())
    return start.date(), (start + timedelta(days=7)).date()


class ClinicBooking(http.Controller):

    def _company(self):
        return request.env.company.sudo().name or _("Clinique")

    def _doctors_with_slots(self):
        Slot = request.env['clinic.slot'].sudo()
        doctors = request.env['clinic.doctor'].sudo().search([('active', '=', True)], order='name')
        return doctors.filtered(lambda doctor: Slot.available_for(doctor))

    def _catalog(self, doctor):
        days = []
        index = {}
        for slot in request.env['clinic.slot'].sudo().available_for(doctor):
            local = utc_to_local(slot.start)
            key = local.strftime('%Y-%m-%d')
            if key not in index:
                index[key] = {
                    'key': key,
                    'label': '%s %s' % (WEEKDAYS[local.weekday()], local.strftime('%d/%m')),
                    'hours': [],
                }
                days.append(index[key])
            index[key]['hours'].append({
                'id': slot.id,
                'label': '%s – %s' % (
                    local.strftime('%H:%M'),
                    utc_to_local(slot.stop).strftime('%H:%M'),
                ),
            })
        return days

    def _values(self, **extra):
        doctor_id = extra.pop('doctor_id', None)
        day = extra.pop('day', None)
        doctors = self._doctors_with_slots()
        doctor = doctors.filtered(lambda item: item.id == doctor_id)[:1]
        days = self._catalog(doctor) if doctor else []
        chosen = next((item for item in days if item['key'] == day), None)
        values = {
            'company': self._company(),
            'doctors': doctors,
            'doctor': doctor,
            'days': days,
            'day': chosen,
            'error': None,
            'form': {},
        }
        values.update(extra)
        return values

    @http.route(['/prendre-rendez-vous'], type='http', auth='public', website=False, sitemap=False)
    def booking_form(self, doctor_id=None, day=None, **kw):
        try:
            doctor_id = int(doctor_id) if doctor_id else None
        except (TypeError, ValueError):
            doctor_id = None
        return request.render('medicalclinic.clinic_booking_page', self._values(
            doctor_id=doctor_id, day=day,
        ))

    @http.route(
        ['/prendre-rendez-vous/envoyer'],
        type='http', auth='public', methods=['POST'], website=False, sitemap=False, csrf=True,
    )
    def booking_submit(self, **kw):
        form = {
            'slot_id': kw.get('slot_id') or '',
            'patient_name': (kw.get('patient_name') or '').strip(),
            'phone': (kw.get('phone') or '').strip(),
            'email': (kw.get('email') or '').strip(),
            'gender': kw.get('gender') or '',
            'notes': (kw.get('notes') or '').strip(),
        }
        try:
            slot_id = int(form['slot_id'])
        except (TypeError, ValueError):
            slot_id = 0
        slot = request.env['clinic.slot'].sudo().browse(slot_id).exists()
        try:
            appointment = request.env['clinic.appointment'].sudo().book_public(
                slot_id,
                form['patient_name'],
                form['phone'],
                form['gender'],
                email=form['email'],
                notes=form['notes'],
            )
        except (UserError, ValidationError) as err:
            local = utc_to_local(slot.start) if slot and slot.start else None
            return request.render('medicalclinic.clinic_booking_page', self._values(
                doctor_id=slot.doctor_id.id if slot else None,
                day=local.strftime('%Y-%m-%d') if local else None,
                error=err.args[0] if err.args else _("La demande n'a pas pu être envoyée."),
                form=form,
            ))
        local = utc_to_local(appointment.appointment_date)
        return request.render('medicalclinic.clinic_booking_done', {
            'company': self._company(),
            'appointment': appointment.sudo(),
            'when': '%s %s' % (WEEKDAYS[local.weekday()], local.strftime('%d/%m/%Y %H:%M')),
        })
