# -*- coding: utf-8 -*-
import pytz
from datetime import datetime, timedelta
from urllib.parse import urlencode

from odoo import fields, http, _
from odoo.exceptions import AccessDenied, AccessError, UserError, ValidationError
from odoo.http import content_disposition, request
from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.utils import ensure_db
from .booking import WEEKDAYS, local_to_utc, utc_to_local, week_bounds

WEB_ROLES = ('receptionist', 'doctor', 'lab')
ROLE_XMLID = {
    'receptionist': 'medicalclinic.group_clinic_receptionist',
    'doctor': 'medicalclinic.group_clinic_doctor',
    'lab': 'medicalclinic.group_clinic_lab',
    'principal': 'medicalclinic.group_clinic_principal',
    'manager': 'medicalclinic.group_clinic_manager',
}
ROLE_LABELS = {
    'receptionist': 'Réception',
    'doctor': 'Médecin',
    'lab': 'Laboratoire',
}
APPOINTMENT_COLUMNS = (
    ('draft', 'Brouillon'),
    ('confirmed', 'Confirmé'),
    ('done', 'Terminé'),
    ('cancel', 'Annulé'),
)
LAB_COLUMNS = (
    ('draft', 'À envoyer'),
    ('in_progress', 'Au laboratoire'),
    ('done', 'Résultats prêts'),
)
MOVES = {
    'receptionist': {
        'appointment': {
            'draft': ('confirmed', 'cancel'),
            'confirmed': ('done', 'cancel', 'draft'),
            'done': ('confirmed',),
            'cancel': ('draft',),
        },
    },
    'doctor': {
        'appointment': {
            'confirmed': ('done',),
        },
        'lab': {
            'draft': ('in_progress',),
        },
    },
    'lab': {
        'lab': {
            'done': ('in_progress',),
        },
    },
}
ACTION_LABELS = {
    ('appointment', 'confirmed'): 'Confirmer',
    ('appointment', 'done'): 'Terminer',
    ('appointment', 'cancel'): 'Annuler',
    ('appointment', 'draft'): 'Remettre en brouillon',
    ('lab', 'in_progress'): 'Envoyer au labo',
    ('lab', 'done'): 'Valider',
    ('lab', 'draft'): 'Rappeler',
}
FORWARD_STATES = {'confirmed', 'done', 'in_progress'}
BOARD_LIMIT = 200
GRID_HOURS = tuple(
    '%02d:%02d' % divmod(minute, 60)
    for minute in range(8 * 60, 18 * 60, 30)
)
GRID_MINUTES = 30


def _is_backend(user):
    return bool(user) and (
        user.has_group(ROLE_XMLID['manager'])
        or user.has_group(ROLE_XMLID['principal'])
    )


def _web_roles(user):
    if not user or _is_backend(user):
        return []
    return [role for role in WEB_ROLES if user.has_group(ROLE_XMLID[role])]


def _session_user():
    uid = request.session.uid
    if not uid:
        return request.env['res.users'].browse()
    return request.env['res.users'].sudo().browse(uid).exists()


class ClinicHome(Home):

    @http.route()
    def index(self, s_action=None, db=None, **kw):
        if _web_roles(_session_user()):
            return request.redirect('/clinic')
        return super().index(s_action=s_action, db=db, **kw)

    @http.route()
    def web_client(self, s_action=None, **kw):
        if _web_roles(_session_user()):
            return request.redirect('/clinic')
        return super().web_client(s_action=s_action, **kw)

    def _login_redirect(self, uid, redirect=None):
        user = request.env['res.users'].sudo().browse(uid)
        if _web_roles(user):
            redirect = '/clinic'
        elif _is_backend(user) and (
            not redirect or (redirect.startswith('/clinic') and not redirect.startswith('/clinic/creneaux'))
        ):
            redirect = '/odoo'
        return super()._login_redirect(uid, redirect=redirect)


class ClinicWeb(http.Controller):

    def _activate_user(self):
        if not request.session.uid:
            return None
        if request.env.uid != request.session.uid:
            request.update_env(user=request.session.uid)
        return request.env.user

    def _roles(self):
        return _web_roles(request.env.user)

    def _query(self, roles, role, **extra):
        params = {}
        if len(roles) > 1 and role:
            params['as'] = role
        for key, value in extra.items():
            if value:
                params[key] = value
        return params

    def _url(self, path, roles, role, **extra):
        params = self._query(roles, role, **extra)
        if not params:
            return path
        return '%s?%s' % (path, urlencode(params))

    def _gate(self, allowed=None, allow_backend=False):
        user = self._activate_user()
        if not user:
            return request.redirect('/clinic/login')
        if _is_backend(user):
            if allow_backend:
                return 'receptionist'
            return request.redirect('/odoo')
        roles = _web_roles(user)
        if not roles:
            return request.redirect('/odoo')
        asked = request.params.get('as')
        role = asked if asked in roles else roles[0]
        if allowed and role not in allowed:
            return request.redirect_query('/clinic', self._query(roles, role))
        return role

    def _shell(self, role):
        roles = self._roles()
        return {
            'company': request.env.company.name,
            'user_name': request.env.user.name,
            'role': role,
            'role_label': ROLE_LABELS[role],
            'roles': [
                {
                    'key': item,
                    'label': ROLE_LABELS[item],
                    'url': self._url('/clinic', roles, item),
                }
                for item in roles
            ],
            'message': request.params.get('message') or '',
            'error': request.params.get('error') or '',
            'tab': '',
            'open_dialog': '',
            'page_title': 'Espace clinique',
            'home_url': '/clinic',
            'board_title': '',
        }

    def _to_board(self, role, **extra):
        if extra.get('tab') == 'consultations':
            extra.pop('tab')
        return request.redirect_query('/clinic', self._query(self._roles(), role, **extra))

    def _safe_next(self, raw):
        if not raw or not raw.startswith('/clinic/') or '//' in raw[:10] or '..' in raw or '\\' in raw:
            return None
        path = raw.split('?', 1)[0]
        if path.startswith('/clinic/login'):
            return None
        return path

    def _back(self, role, next_path=None, **extra):
        path = self._safe_next(next_path)
        if not path:
            return self._to_board(role, **extra)
        if extra.get('tab') == 'consultations':
            extra.pop('tab')
        return request.redirect_query(path, self._query(self._roles(), role, **extra))

    def _user_error(self, err):
        if getattr(err, 'args', None):
            return err.args[0]
        return _("Action impossible.")

    def _tz(self):
        name = request.env.user.tz or 'UTC'
        try:
            return pytz.timezone(name)
        except pytz.UnknownTimeZoneError:
            return pytz.UTC

    def _fmt_dt(self, value):
        if not value:
            return ''
        return fields.Datetime.context_timestamp(request.env.user, value).strftime('%d/%m/%Y %H:%M')

    def _fmt_input(self, value):
        if not value:
            return ''
        return fields.Datetime.context_timestamp(request.env.user, value).strftime('%Y-%m-%dT%H:%M')

    def _parse_dt(self, raw):
        raw = (raw or '').strip().replace(' ', 'T')
        if not raw:
            raise UserError(_("La date est obligatoire."))
        try:
            naive = datetime.strptime(raw[:16], '%Y-%m-%dT%H:%M')
        except ValueError as exc:
            raise UserError(_("Date invalide.")) from exc
        return self._tz().localize(naive).astimezone(pytz.UTC).replace(tzinfo=None)

    def _parse_date(self, raw):
        if not raw:
            return False
        try:
            return fields.Date.to_date(raw)
        except (ValueError, TypeError) as exc:
            raise UserError(_("Date de naissance invalide.")) from exc

    def _int_id(self, raw, label):
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise UserError(_("%s est obligatoire.") % label) from exc
        if value <= 0:
            raise UserError(_("%s est obligatoire.") % label)
        return value

    def _record(self, model, res_id):
        res_id = self._int_id(res_id, _("Dossier"))
        model_name = 'clinic.appointment' if model == 'appointment' else 'clinic.lab.request'
        if model not in ('appointment', 'lab'):
            raise UserError(_("Élément inconnu."))
        record = request.env[model_name].search([('id', '=', res_id)], limit=1)
        if not record:
            raise UserError(_("Élément introuvable."))
        return record

    def _apply_move(self, role, model, res_id, state):
        allowed = MOVES.get(role, {}).get(model, {})
        record = self._record(model, res_id)
        if state not in allowed.get(record.state, ()):
            raise UserError(_("Ce déplacement n'est pas autorisé."))
        record.action_set_state(state)

    def _doctor_profile(self):
        return request.env['clinic.doctor'].search([
            ('user_id', '=', request.env.uid),
        ], limit=1)

    def _selection_label(self, record, field_name):
        if not record or not record[field_name]:
            return ''
        selection = record._fields[field_name].selection
        if callable(selection):
            selection = selection(record)
        return dict(selection).get(record[field_name], '')

    def _actions_for(self, role, model, state):
        actions = []
        for target in MOVES.get(role, {}).get(model, {}).get(state, ()):
            label = ACTION_LABELS.get((model, target), target)
            if target == 'draft' and state == 'cancel':
                label = 'Réactiver'
            elif target == 'draft' and state == 'confirmed':
                label = 'Remettre en brouillon'
            elif target == 'confirmed' and state == 'done':
                label = 'Rouvrir'
            elif target == 'in_progress' and state == 'done':
                label = 'Corriger'
            actions.append({
                'state': target,
                'label': label,
                'primary': target in FORWARD_STATES and not (target == 'in_progress' and state == 'done'),
            })
        return actions

    def _appointment_card(self, rec, roles, role):
        moves = MOVES.get(role, {}).get('appointment', {}).get(rec.state, ())
        phone = rec.patient_id.phone or ''
        return {
            'id': rec.id,
            'model': 'appointment',
            'href': self._url('/clinic/appointment/%s' % rec.id, roles, role),
            'ref': rec.name,
            'title': rec.patient_id.name,
            'subtitle': rec.doctor_id.name,
            'meta': '%s · Site web' % phone if rec.booked_online and phone else (phone or (_("Site web") if rec.booked_online else '')),
            'when': self._fmt_dt(rec.appointment_date),
            'note': (rec.notes or '').strip(),
            'state': rec.state,
            'moves': ','.join(moves),
            'actions': self._actions_for(role, 'appointment', rec.state),
        }

    def _lab_card(self, rec, roles, role):
        moves = MOVES.get(role, {}).get('lab', {}).get(rec.state, ())
        return {
            'id': rec.id,
            'model': 'lab',
            'href': self._url('/clinic/lab/%s' % rec.id, roles, role),
            'ref': rec.name,
            'title': rec.patient_id.name,
            'subtitle': rec.doctor_id.name,
            'meta': rec.exam_summary(),
            'when': self._fmt_dt(rec.date),
            'note': (rec.notes or '').strip(),
            'state': rec.state,
            'moves': ','.join(moves),
            'actions': self._actions_for(role, 'lab', rec.state),
            'voucher_url': self._url('/clinic/lab/%s/bon' % rec.id, roles, role) if role == 'lab' and rec.state != 'draft' else '',
        }

    def _columns(self, specs, records, card_builder):
        grouped = {key: [] for key, _label in specs}
        for rec in records:
            if rec.state in grouped:
                grouped[rec.state].append(card_builder(rec))
        return [
            {
                'key': key,
                'label': label,
                'count': len(grouped[key]),
                'cards': grouped[key],
            }
            for key, label in specs
        ]

    def _search_domain(self, q):
        if not q:
            return []
        return ['|', '|', '|',
                ('name', 'ilike', q),
                ('patient_id.name', 'ilike', q),
                ('doctor_id.name', 'ilike', q),
                ('notes', 'ilike', q)]

    def _options(self):
        patients = request.env['clinic.patient'].search([], order='name')
        doctors = request.env['clinic.doctor'].search([], order='name')
        return {
            'patients': [{'id': rec.id, 'name': rec.name} for rec in patients],
            'doctors': [{
                'id': rec.id,
                'name': '%s — %s' % (rec.name, rec.specialty or ''),
            } for rec in doctors],
            'exams': [
                {'check': check, 'label': label, 'detail': detail}
                for check, _code, label, detail in request.env['clinic.lab.request'].EXAM_SPECS
            ],
            'blood_groups': [
                key for key, _label in request.env['clinic.patient']._fields['blood_group'].selection
            ],
        }

    @http.route('/clinic/login', type='http', auth='none', readonly=False, sitemap=False)
    def clinic_login(self, **kw):
        ensure_db()
        if request.env.uid is None:
            if request.session.uid:
                request.update_env(user=request.session.uid)
            else:
                request.env['ir.http']._auth_method_public()

        if request.httprequest.method == 'GET' and request.session.uid:
            return request.redirect(self._landing(request.session.uid))

        error = None
        if request.params.get('error') == 'role':
            error = _("Ce compte n'a pas accès à l'espace clinique.")
        login = kw.get('login') or request.params.get('login') or ''
        if request.httprequest.method == 'POST':
            try:
                auth_info = request.session.authenticate(request.env, {
                    'type': 'password',
                    'login': kw.get('login') or '',
                    'password': kw.get('password') or '',
                })
                return request.redirect(self._landing(auth_info['uid']))
            except AccessDenied:
                error = _("Identifiant ou mot de passe incorrect.")

        response = request.render('medicalclinic.clinic_login', {
            'error': error,
            'login': login,
            'company': request.env.company.name,
        })
        response.headers['Cache-Control'] = 'no-store'
        return response

    def _landing(self, uid):
        if not request.session.uid:
            return '/web/login'
        user = request.env['res.users'].sudo().browse(uid)
        if _is_backend(user):
            return '/odoo'
        if _web_roles(user):
            return '/clinic'
        request.session.logout(keep_db=True)
        return '/clinic/login?error=role'

    @http.route('/clinic/logout', type='http', auth='public', methods=['POST'], sitemap=False)
    def clinic_logout(self, **kw):
        if request.session.uid:
            request.session.logout(keep_db=True)
        return request.redirect('/clinic/login')

    @http.route('/clinic', type='http', auth='public', sitemap=False)
    def board(self, **kw):
        role = self._gate()
        if not isinstance(role, str):
            return role
        roles = self._roles()
        q = (kw.get('q') or '').strip()
        tab = kw.get('tab') if kw.get('tab') in ('consultations', 'analyses') else 'consultations'
        values = self._shell(role)
        values.update({
            'q': q,
            'tab': tab,
            'truncated': False,
            'profile_missing': False,
            'appointments': [],
            'open_dialog': kw.get('open') if kw.get('open') in ('dlg-patient', 'dlg-appointment', 'dlg-lab') else '',
            'pending_slots': [],
        })
        values.update(self._options())
        domain = self._search_domain(q)
        if role == 'receptionist':
            records = request.env['clinic.appointment'].search(domain, order='appointment_date asc', limit=BOARD_LIMIT + 1)
            values['truncated'] = len(records) > BOARD_LIMIT
            values['columns'] = self._columns(
                APPOINTMENT_COLUMNS,
                records[:BOARD_LIMIT],
                lambda rec: self._appointment_card(rec, roles, role),
            )
            values['board_title'] = 'Rendez-vous'
            values['board_hint'] = 'Glissez une carte vers une autre colonne, ou utilisez les boutons.'
        elif role == 'doctor':
            profile = self._doctor_profile()
            values['profile_missing'] = not profile
            if profile:
                pending = request.env['clinic.slot'].search([
                    ('doctor_id', '=', profile.id),
                    ('state', '=', 'sent'),
                    ('appointment_id', '=', False),
                    ('start', '>', fields.Datetime.now()),
                ], order='start')
                values['pending_slots'] = self._slot_rows_for(pending, 'doctor')
            if tab == 'analyses':
                records = request.env['clinic.lab.request'].search(domain, order='date asc', limit=BOARD_LIMIT + 1)
                values['columns'] = self._columns(
                    LAB_COLUMNS,
                    records[:BOARD_LIMIT],
                    lambda rec: self._lab_card(rec, roles, role),
                )
                values['board_title'] = 'Demandes d\'analyses'
                values['board_hint'] = 'Préparez la demande, puis envoyez-la au laboratoire.'
            else:
                records = request.env['clinic.appointment'].search(
                    [('state', '!=', 'cancel')] + domain,
                    order='appointment_date asc',
                    limit=BOARD_LIMIT + 1,
                )
                values['columns'] = self._columns(
                    APPOINTMENT_COLUMNS[:3],
                    records[:BOARD_LIMIT],
                    lambda rec: self._appointment_card(rec, roles, role),
                )
                values['board_title'] = 'Consultations'
                values['board_hint'] = 'Ouvrez une consultation pour le compte rendu et la prescription.'
            values['truncated'] = len(records) > BOARD_LIMIT
            values['appointments'] = [{
                'id': rec.id,
                'label': '%s — %s — %s' % (rec.name, rec.patient_id.name, self._fmt_dt(rec.appointment_date)),
            } for rec in request.env['clinic.appointment'].search([
                ('state', 'in', ('confirmed', 'done')),
            ], order='appointment_date desc', limit=40)]
        else:
            records = request.env['clinic.lab.request'].search(domain, order='date asc', limit=BOARD_LIMIT + 1)
            values['truncated'] = len(records) > BOARD_LIMIT
            values['columns'] = self._columns(
                LAB_COLUMNS[1:],
                records[:BOARD_LIMIT],
                lambda rec: self._lab_card(rec, roles, role),
            )
            values['board_title'] = 'File du laboratoire'
            values['board_hint'] = 'Ouvrez une demande pour saisir les résultats, puis validez.'
        values['page_title'] = values.get('board_title') or 'Espace clinique'
        values['consult_url'] = self._url('/clinic', roles, role)
        values['analyses_url'] = self._url('/clinic', roles, role, tab='analyses')
        values['slots_url'] = self._url('/clinic/creneaux', roles, role)
        return request.render('medicalclinic.clinic_board', values)

    @http.route('/clinic/patient/create', type='http', auth='public', methods=['POST'], sitemap=False)
    def create_patient(self, **kw):
        role = self._gate(('receptionist',))
        if not isinstance(role, str):
            return role
        try:
            name = (kw.get('name') or '').strip()
            if not name:
                raise UserError(_("Le nom du patient est obligatoire."))
            gender = kw.get('gender')
            if gender not in ('male', 'female'):
                raise UserError(_("Indiquez le sexe du patient."))
            blood = kw.get('blood_group') or False
            allowed_blood = {key for key, _label in request.env['clinic.patient']._fields['blood_group'].selection}
            if blood and blood not in allowed_blood:
                blood = False
            request.env['clinic.patient'].create({
                'name': name[:128],
                'gender': gender,
                'dob': self._parse_date(kw.get('dob')),
                'phone': (kw.get('phone') or '').strip()[:32] or False,
                'email': (kw.get('email') or '').strip()[:128] or False,
                'blood_group': blood,
            })
        except (UserError, AccessError, ValidationError) as err:
            return self._to_board(role, error=self._user_error(err), open='dlg-patient')
        return self._to_board(role, message=_("Patient enregistré."))

    @http.route('/clinic/appointment/create', type='http', auth='public', methods=['POST'], sitemap=False)
    def create_appointment(self, **kw):
        role = self._gate(('receptionist',))
        if not isinstance(role, str):
            return role
        try:
            patient = request.env['clinic.patient'].search([
                ('id', '=', self._int_id(kw.get('patient_id'), _("Patient"))),
            ], limit=1)
            doctor = request.env['clinic.doctor'].search([
                ('id', '=', self._int_id(kw.get('doctor_id'), _("Médecin"))),
            ], limit=1)
            if not patient or not doctor:
                raise UserError(_("Patient ou médecin introuvable."))
            request.env['clinic.appointment'].create({
                'patient_id': patient.id,
                'doctor_id': doctor.id,
                'appointment_date': self._parse_dt(kw.get('appointment_date')),
                'notes': (kw.get('notes') or '').strip()[:4000] or False,
            })
        except (UserError, AccessError, ValidationError) as err:
            return self._to_board(role, error=self._user_error(err), open='dlg-appointment')
        return self._to_board(role, message=_("Rendez-vous créé."))

    @http.route('/clinic/lab/create', type='http', auth='public', methods=['POST'], sitemap=False)
    def create_lab(self, **kw):
        role = self._gate(('doctor',))
        if not isinstance(role, str):
            return role
        try:
            profile = self._doctor_profile()
            if not profile:
                raise UserError(_("Votre compte n'est pas relié à une fiche médecin."))
            patient = request.env['clinic.patient'].search([
                ('id', '=', self._int_id(kw.get('patient_id'), _("Patient"))),
            ], limit=1)
            if not patient:
                raise UserError(_("Patient introuvable."))
            vals = {
                'patient_id': patient.id,
                'doctor_id': profile.id,
            }
            if kw.get('appointment_id'):
                appointment = request.env['clinic.appointment'].search([
                    ('id', '=', self._int_id(kw.get('appointment_id'), _("Rendez-vous"))),
                    ('doctor_id', '=', profile.id),
                ], limit=1)
                if appointment:
                    vals['appointment_id'] = appointment.id
                    vals['patient_id'] = appointment.patient_id.id
            for check, _code, _label, _detail in request.env['clinic.lab.request'].EXAM_SPECS:
                vals[check] = kw.get(check) in ('1', 'on', 'true')
            if not any(vals[check] for check, _code, _label, _detail in request.env['clinic.lab.request'].EXAM_SPECS):
                raise UserError(_("Cochez au moins un examen."))
            request.env['clinic.lab.request'].create(vals)
        except (UserError, AccessError, ValidationError) as err:
            if kw.get('next'):
                return self._back(role, kw.get('next'), error=self._user_error(err))
            return self._to_board(role, error=self._user_error(err), tab='analyses', open='dlg-lab')
        if kw.get('next'):
            return self._back(role, kw.get('next'), message=_("Demande d'analyse créée."))
        return self._to_board(role, message=_("Demande d'analyse créée."), tab='analyses')

    @http.route('/clinic/move', type='http', auth='public', methods=['POST'], sitemap=False)
    def move_form(self, **kw):
        role = self._gate()
        if not isinstance(role, str):
            return role
        try:
            self._apply_move(role, kw.get('model'), kw.get('res_id'), kw.get('state'))
        except (UserError, AccessError, ValidationError) as err:
            return self._back(role, kw.get('next'), error=self._user_error(err), tab=kw.get('tab'))
        return self._back(role, kw.get('next'), message=_("Statut mis à jour."), tab=kw.get('tab'))

    @http.route('/clinic/kanban/move', type='jsonrpc', auth='user', methods=['POST'], sitemap=False)
    def move_json(self, model, res_id, state, role=None):
        roles = _web_roles(request.env.user)
        if not roles or _is_backend(request.env.user):
            raise AccessError(_("Accès refusé."))
        if role not in roles:
            role = roles[0]
        self._apply_move(role, model, res_id, state)
        return {'ok': True}

    @http.route('/clinic/appointment/<int:appointment_id>', type='http', auth='public', sitemap=False)
    def appointment_page(self, appointment_id, **kw):
        role = self._gate(('receptionist', 'doctor'))
        if not isinstance(role, str):
            return role
        appointment = request.env['clinic.appointment'].search([('id', '=', appointment_id)], limit=1)
        if not appointment:
            return request.not_found()
        roles = self._roles()
        patient = appointment.patient_id
        values = self._shell(role)
        values.update(self._options())
        values.update({
            'appointment': appointment,
            'page_title': appointment.name,
            'state_label': dict(APPOINTMENT_COLUMNS).get(appointment.state, appointment.state),
            'when': self._fmt_dt(appointment.appointment_date),
            'when_input': self._fmt_input(appointment.appointment_date),
            'gender': self._selection_label(patient, 'gender'),
            'blood': self._selection_label(patient, 'blood_group'),
            'back_url': self._url('/clinic', roles, role),
            'labs': [{
                'id': lab.id,
                'name': lab.name,
                'summary': lab.exam_summary(),
                'state': lab.state,
                'href': self._url('/clinic/lab/%s' % lab.id, roles, role),
            } for lab in appointment.env['clinic.lab.request'].search([
                ('appointment_id', '=', appointment.id),
            ], order='date desc')],
            'actions': self._actions_for(role, 'appointment', appointment.state),
            'next_url': '/clinic/appointment/%s' % appointment.id,
            'prescriptions': [{
                'id': item.id,
                'name': item.name,
                'when': self._fmt_dt(item.date),
                'count': len(item.line_ids),
                'href': self._url('/clinic/prescription/%s' % item.id, roles, role),
            } for item in appointment.prescription_ids.sorted('date', reverse=True)],
        })
        return request.render('medicalclinic.clinic_appointment_page', values)

    @http.route('/clinic/appointment/<int:appointment_id>/update', type='http', auth='public', methods=['POST'], sitemap=False)
    def update_appointment(self, appointment_id, **kw):
        role = self._gate(('receptionist', 'doctor'))
        if not isinstance(role, str):
            return role
        next_url = '/clinic/appointment/%s' % appointment_id
        try:
            appointment = self._record('appointment', appointment_id)
            if role == 'doctor':
                if appointment.state not in ('confirmed', 'done'):
                    raise UserError(_("Le compte rendu se saisit sur une consultation confirmée."))
                appointment.write({
                    'consultation_notes': (kw.get('consultation_notes') or '').strip()[:8000] or False,
                })
            else:
                if appointment.state not in ('draft', 'confirmed'):
                    raise UserError(_("Ce rendez-vous ne peut plus être modifié."))
                patient = request.env['clinic.patient'].search([
                    ('id', '=', self._int_id(kw.get('patient_id'), _("Patient"))),
                ], limit=1)
                doctor = request.env['clinic.doctor'].search([
                    ('id', '=', self._int_id(kw.get('doctor_id'), _("Médecin"))),
                ], limit=1)
                if not patient or not doctor:
                    raise UserError(_("Patient ou médecin introuvable."))
                appointment.write({
                    'patient_id': patient.id,
                    'doctor_id': doctor.id,
                    'appointment_date': self._parse_dt(kw.get('appointment_date')),
                    'notes': (kw.get('notes') or '').strip()[:4000] or False,
                })
        except (UserError, AccessError, ValidationError) as err:
            return self._back(role, next_url, error=self._user_error(err))
        return self._back(role, next_url, message=_("Rendez-vous mis à jour."))

    def _medication_choices(self):
        meds = request.env['clinic.medication'].search([])
        classes = dict(meds._fields['drug_class'].selection)
        forms = dict(meds._fields['form'].selection)
        return [{
            'id': med.id,
            'label': med.display_name,
            'search': (med.search_text or med.display_name or '').lower(),
            'klass': classes.get(med.drug_class, ''),
            'form': forms.get(med.form, ''),
        } for med in meds]

    def _prescription_for_doctor(self, prescription_id):
        prescription = request.env['clinic.prescription'].search([
            ('id', '=', prescription_id),
        ], limit=1)
        if not prescription:
            return None
        return prescription

    @http.route('/clinic/appointment/<int:appointment_id>/prescription', type='http', auth='public', methods=['POST'], sitemap=False)
    def create_prescription(self, appointment_id, **kw):
        role = self._gate(('doctor',))
        if not isinstance(role, str):
            return role
        next_url = '/clinic/appointment/%s' % appointment_id
        try:
            appointment = self._record('appointment', appointment_id)
            if appointment.state not in ('confirmed', 'done'):
                raise UserError(_("L'ordonnance se rédige sur une consultation confirmée."))
            profile = self._doctor_profile()
            if not profile or appointment.doctor_id != profile:
                raise UserError(_("Cette consultation n'est pas la vôtre."))
            prescription = request.env['clinic.prescription'].create({
                'patient_id': appointment.patient_id.id,
                'doctor_id': profile.id,
                'appointment_id': appointment.id,
            })
        except (UserError, AccessError, ValidationError) as err:
            return self._back(role, next_url, error=self._user_error(err))
        return request.redirect(self._url(
            '/clinic/prescription/%s' % prescription.id, self._roles(), role,
        ))

    @http.route('/clinic/prescription/<int:prescription_id>', type='http', auth='public', sitemap=False)
    def prescription_page(self, prescription_id, **kw):
        role = self._gate(('doctor',))
        if not isinstance(role, str):
            return role
        prescription = self._prescription_for_doctor(prescription_id)
        if not prescription:
            return request.not_found()
        roles = self._roles()
        patient = prescription.patient_id
        back = '/clinic/appointment/%s' % prescription.appointment_id.id if prescription.appointment_id else '/clinic'
        values = self._shell(role)
        values.update({
            'prescription': prescription,
            'page_title': prescription.name,
            'when': self._fmt_dt(prescription.date),
            'gender': self._selection_label(patient, 'gender'),
            'medications': self._medication_choices(),
            'back_url': self._url(back, roles, role),
            'pdf_url': self._url('/clinic/prescription/%s/pdf' % prescription.id, roles, role),
            'lines': [{
                'id': line.id,
                'label': line.medication_id.display_name,
                'dosage': line.dosage,
                'duration': line.duration or '',
                'quantity': line.quantity or '',
                'instructions': line.instructions or '',
            } for line in prescription.line_ids],
        })
        return request.render('medicalclinic.clinic_prescription_page', values)

    @http.route('/clinic/prescription/<int:prescription_id>/save', type='http', auth='public', methods=['POST'], sitemap=False)
    def save_prescription(self, prescription_id, **kw):
        role = self._gate(('doctor',))
        if not isinstance(role, str):
            return role
        next_url = '/clinic/prescription/%s' % prescription_id
        try:
            prescription = self._prescription_for_doctor(prescription_id)
            if not prescription:
                raise UserError(_("Ordonnance introuvable."))
            action = kw.get('action') or 'line'
            if action == 'notes':
                prescription.notes = (kw.get('notes') or '').strip()[:4000] or False
                message = _("Conseils enregistrés.")
            elif action == 'remove':
                line = prescription.line_ids.filtered(lambda item: item.id == self._int_id(kw.get('line_id'), _("Ligne")))
                if not line:
                    raise UserError(_("Ligne introuvable."))
                line.unlink()
                message = _("Médicament retiré.")
            else:
                medication = request.env['clinic.medication'].search([
                    ('id', '=', self._int_id(kw.get('medication_id'), _("Médicament"))),
                ], limit=1)
                if not medication:
                    raise UserError(_("Choisissez un médicament dans la liste."))
                dosage = (kw.get('dosage') or '').strip()
                if not dosage:
                    raise UserError(_("Indiquez la posologie."))
                request.env['clinic.prescription.line'].create({
                    'prescription_id': prescription.id,
                    'medication_id': medication.id,
                    'dosage': dosage[:120],
                    'duration': (kw.get('duration') or '').strip()[:80] or False,
                    'quantity': (kw.get('quantity') or '').strip()[:80] or False,
                    'instructions': (kw.get('instructions') or '').strip()[:160] or False,
                })
                message = _("Médicament ajouté.")
        except (UserError, AccessError, ValidationError) as err:
            return self._back(role, next_url, error=self._user_error(err))
        return self._back(role, next_url, message=message)

    @http.route('/clinic/prescription/<int:prescription_id>/pdf', type='http', auth='public', sitemap=False)
    def prescription_pdf(self, prescription_id, **kw):
        role = self._gate(('doctor',))
        if not isinstance(role, str):
            return role
        prescription = self._prescription_for_doctor(prescription_id)
        if not prescription:
            return request.not_found()
        if not prescription.line_ids:
            return self._back(
                role, '/clinic/prescription/%s' % prescription.id,
                error=_("Ajoutez au moins un médicament avant d'imprimer."),
            )
        pdf, _report_type = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'medicalclinic.action_report_clinic_prescription', prescription.ids,
        )
        filename = 'Ordonnance_%s.pdf' % (prescription.name or str(prescription.id)).replace('/', '-').replace('\\', '-')
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition(filename)),
        ])

    @http.route('/clinic/prescription/<int:prescription_id>/email', type='http', auth='public', methods=['POST'], sitemap=False)
    def prescription_email(self, prescription_id, **kw):
        role = self._gate(('doctor',))
        if not isinstance(role, str):
            return role
        next_url = '/clinic/prescription/%s' % prescription_id
        try:
            prescription = self._prescription_for_doctor(prescription_id)
            if not prescription:
                raise UserError(_("Ordonnance introuvable."))
            prescription._send_prescription_email()
        except (UserError, AccessError, ValidationError) as err:
            return self._back(role, next_url, error=self._user_error(err))
        return self._back(
            role, next_url,
            message=_("Ordonnance envoyée à %s.") % prescription.patient_id.email,
        )

    @http.route('/clinic/lab/<int:lab_id>', type='http', auth='public', sitemap=False)
    def lab_page(self, lab_id, **kw):
        role = self._gate(('doctor', 'lab'))
        if not isinstance(role, str):
            return role
        lab = request.env['clinic.lab.request'].search([('id', '=', lab_id)], limit=1)
        if not lab:
            return request.not_found()
        roles = self._roles()
        tab = 'analyses' if role == 'doctor' else None
        values = self._shell(role)
        values.update({
            'lab': lab,
            'page_title': lab.name,
            'state_label': dict(LAB_COLUMNS).get(lab.state, lab.state),
            'when': self._fmt_dt(lab.date),
            'lines': lab.exam_lines(),
            'back_url': self._url('/clinic', roles, role, tab=tab),
            'actions': self._actions_for(role, 'lab', lab.state),
            'next_url': '/clinic/lab/%s' % lab.id,
            'can_edit_checks': role == 'doctor' and lab.state == 'draft',
            'can_edit_results': role == 'lab' and lab.state == 'in_progress',
            'pdf_url': self._url('/clinic/lab/%s/pdf' % lab.id, roles, role) if role == 'lab' else '',
            'voucher_url': self._url('/clinic/lab/%s/bon' % lab.id, roles, role) if lab.state != 'draft' else '',
            'exams': [
                {'check': check, 'label': label, 'detail': detail, 'checked': bool(lab[check])}
                for check, _code, label, detail in lab.EXAM_SPECS
            ],
        })
        return request.render('medicalclinic.clinic_lab_page', values)

    @http.route('/clinic/lab/<int:lab_id>/save', type='http', auth='public', methods=['POST'], sitemap=False)
    def save_lab(self, lab_id, **kw):
        role = self._gate(('doctor', 'lab'))
        if not isinstance(role, str):
            return role
        next_url = '/clinic/lab/%s' % lab_id
        tab = 'analyses' if role == 'doctor' else None
        try:
            lab = self._record('lab', lab_id)
            action = kw.get('action') or 'save'
            if role == 'doctor':
                if lab.state != 'draft':
                    raise UserError(_("La prescription n'est plus modifiable."))
                vals = {}
                for check, _code, _label, _detail in lab.EXAM_SPECS:
                    vals[check] = kw.get(check) in ('1', 'on', 'true')
                if action == 'send':
                    vals['state'] = 'in_progress'
                lab.write(vals)
                message = _("Demande envoyée au laboratoire.") if action == 'send' else _("Prescription enregistrée.")
            else:
                if lab.state != 'in_progress':
                    raise UserError(_("Ces résultats ne sont plus modifiables."))
                for line in lab.line_ids:
                    raw = kw.get('line_%s' % line.id)
                    if raw is not None:
                        line.result = raw.strip()[:64]
                vals = {'notes': (kw.get('notes') or '').strip()[:4000] or False}
                if action == 'done':
                    vals['state'] = 'done'
                lab.write(vals)
                message = _("Résultats validés.") if action == 'done' else _("Résultats enregistrés.")
        except (UserError, AccessError, ValidationError) as err:
            return self._back(role, next_url, error=self._user_error(err), tab=tab)
        if action in ('send', 'done'):
            return self._to_board(role, message=message, tab=tab)
        return self._back(role, next_url, message=message, tab=tab)

    @http.route('/clinic/lab/<int:lab_id>/bon', type='http', auth='public', sitemap=False)
    def lab_voucher(self, lab_id, **kw):
        role = self._gate(('doctor', 'lab'))
        if not isinstance(role, str):
            return role
        lab = request.env['clinic.lab.request'].search([('id', '=', lab_id)], limit=1)
        if not lab or lab.state == 'draft':
            return request.not_found()
        pdf, _report_type = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'medicalclinic.action_report_clinic_lab_voucher', lab.ids,
        )
        filename = 'Bon_%s.pdf' % (lab.name or str(lab.id)).replace('/', '-').replace('\\', '-')
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition(filename)),
        ])

    @http.route('/clinic/lab/<int:lab_id>/pdf', type='http', auth='public', sitemap=False)
    def lab_pdf(self, lab_id, **kw):
        role = self._gate(('lab',))
        if not isinstance(role, str):
            return role
        lab = request.env['clinic.lab.request'].search([('id', '=', lab_id)], limit=1)
        if not lab:
            return request.not_found()
        pdf, _report_type = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'medicalclinic.action_report_clinic_lab_request', lab.ids,
        )
        filename = 'Analyse_%s.pdf' % (lab.name or str(lab.id)).replace('/', '-').replace('\\', '-')
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition(filename)),
        ])

    @http.route('/clinic/lab/<int:lab_id>/email', type='http', auth='public', methods=['POST'], sitemap=False)
    def lab_email(self, lab_id, **kw):
        role = self._gate(('lab',))
        if not isinstance(role, str):
            return role
        next_url = '/clinic/lab/%s' % lab_id
        try:
            lab = self._record('lab', lab_id)
            lab._send_results_email()
        except (UserError, AccessError, ValidationError) as err:
            return self._back(role, next_url, error=self._user_error(err))
        return self._back(
            role, next_url,
            message=_("E-mail envoyé à %s.") % lab.patient_id.email,
        )

    def _slot_redirect(self, role, week, **extra):
        return request.redirect_query('/clinic/creneaux', self._query(
            self._roles(), role, week=week, **extra,
        ))

    def _slot_rows(self, slots):
        labels = dict(request.env['clinic.slot']._fields['state'].selection)
        rows = []
        for slot in slots:
            start = utc_to_local(slot.start)
            stop = utc_to_local(slot.stop)
            rows.append({
                'id': slot.id,
                'state': slot.state,
                'state_label': labels.get(slot.state, slot.state),
                'when': '%s %s %s–%s' % (
                    WEEKDAYS[start.weekday()], start.strftime('%d/%m'),
                    start.strftime('%H:%M'), stop.strftime('%H:%M'),
                ),
                'doctor': slot.doctor_id.name,
                'patient': slot.appointment_id.patient_id.name if slot.appointment_id else '',
                'day': start.strftime('%Y-%m-%d'),
                'start_hour': start.strftime('%H:%M'),
                'stop_hour': stop.strftime('%H:%M'),
                'can_edit': not slot.appointment_id and slot.state in ('sent', 'confirmed'),
                'can_confirm': slot.state == 'sent' and not slot.appointment_id,
            })
        return rows

    def _slot_rows_for(self, slots, role):
        rows = self._slot_rows(slots)
        if role != 'doctor':
            for row in rows:
                row['can_edit'] = False
                row['can_confirm'] = False
        return rows

    @http.route('/clinic/creneaux', type='http', auth='public', sitemap=False)
    def slots_page(self, week=None, doctor_id=None, **kw):
        role = self._gate(('receptionist', 'doctor'), allow_backend=True)
        if not isinstance(role, str):
            return role
        today = utc_to_local(fields.Datetime.now()).date()
        try:
            week_start, week_end = week_bounds(week or today.isoformat())
        except ValueError:
            week_start, week_end = week_bounds(today.isoformat())
        week_key = week_start.isoformat()
        doctors = request.env['clinic.doctor'].search([('active', '=', True)], order='name')
        selected = request.env['clinic.doctor']
        if role == 'doctor':
            selected = self._doctor_profile()
        elif doctor_id:
            selected = doctors.filtered(lambda doctor: str(doctor.id) == str(doctor_id))[:1]
        elif doctors:
            selected = doctors[:1]
        start_utc = local_to_utc(week_key, '00:00')
        end_utc = local_to_utc(week_end.isoformat(), '00:00')
        domain = [('start', '>=', start_utc), ('start', '<', end_utc)]
        if selected:
            domain.append(('doctor_id', '=', selected.id))
        slots = request.env['clinic.slot'].search(domain) if selected or role == 'receptionist' else request.env['clinic.slot']
        if role == 'doctor' and not selected:
            slots = request.env['clinic.slot']
        grid_days, grid_rows, extra = self._slot_grid(week_start, slots)
        roles = self._roles()
        values = self._shell(role)
        values.update({
            'page_title': 'Créneaux',
            'week': week_key,
            'week_end': (week_end - timedelta(days=1)).isoformat(),
            'week_label': 'Semaine du %s' % week_start.strftime('%d/%m/%Y'),
            'doctors': doctors,
            'selected_doctor': selected,
            'slots': self._slot_rows_for(slots if role == 'doctor' else extra, role),
            'grid_days': grid_days,
            'grid_rows': grid_rows,
            'draft_count': len(slots.filtered(lambda slot: slot.state == 'draft')),
            'prev_url': self._url('/clinic/creneaux', roles, role, week=(week_start - timedelta(days=7)).isoformat(), doctor_id=selected.id or ''),
            'next_url': self._url('/clinic/creneaux', roles, role, week=(week_start + timedelta(days=7)).isoformat(), doctor_id=selected.id or ''),
            'board_url': '/odoo' if _is_backend(request.env.user) else self._url('/clinic', roles, role),
            'home_url': '/odoo' if _is_backend(request.env.user) else '/clinic',
        })
        return request.render('medicalclinic.clinic_slots_page', values)

    def _slot_grid(self, week_start, slots):
        days = []
        allowed = set()
        for offset in range(7):
            day = week_start + timedelta(days=offset)
            key = day.isoformat()
            allowed.add(key)
            days.append({
                'key': key,
                'label': '%s %s' % (WEEKDAYS[day.weekday()][:3].capitalize(), day.strftime('%d/%m')),
            })
        cells = {}
        extra = request.env['clinic.slot']
        for slot in slots:
            start = utc_to_local(slot.start)
            stop = utc_to_local(slot.stop)
            day_key = start.strftime('%Y-%m-%d')
            hour = start.strftime('%H:%M')
            minutes = int((stop - start).total_seconds() // 60)
            if day_key not in allowed or hour not in GRID_HOURS or minutes != GRID_MINUTES:
                extra |= slot
                continue
            if slot.appointment_id:
                kind = 'booked'
                title = slot.appointment_id.patient_id.name or _("Réservé")
            elif slot.state == 'sent':
                kind = 'sent'
                title = _("Envoyé au médecin")
            elif slot.state == 'confirmed':
                kind = 'confirmed'
                title = _("Confirmé")
            else:
                kind = 'draft'
                title = _("Brouillon")
            cells['%s|%s' % (day_key, hour)] = {
                'locked': slot.state != 'draft' or bool(slot.appointment_id),
                'kind': kind,
                'title': title,
            }
        rows = []
        for hour in GRID_HOURS:
            row_cells = []
            for day in days:
                cell = cells.get('%s|%s' % (day['key'], hour)) or {}
                row_cells.append({
                    'value': '%s|%s' % (day['key'], hour),
                    'day': day['key'],
                    'checked': bool(cell),
                    'locked': bool(cell.get('locked')),
                    'kind': cell.get('kind') or '',
                    'title': cell.get('title') or '',
                })
            rows.append({'hour': hour, 'cells': row_cells})
        return days, rows, extra

    @http.route('/clinic/creneaux/grille', type='http', auth='public', methods=['POST'], sitemap=False)
    def slots_fill(self, **kw):
        role = self._gate(('receptionist',), allow_backend=True)
        if not isinstance(role, str):
            return role
        week = kw.get('week') or ''
        doctor_id = kw.get('doctor_id')
        try:
            doctor = request.env['clinic.doctor'].browse(int(doctor_id)).exists()
            if not doctor or not doctor.active:
                raise UserError(_("Choisissez un médecin."))
            week_start, week_end = week_bounds(week)
            allowed_days = {(week_start + timedelta(days=offset)).isoformat() for offset in range(7)}
            wanted = set()
            for raw in request.httprequest.form.getlist('cells'):
                day, _sep, hour = (raw or '').partition('|')
                if day in allowed_days and hour in GRID_HOURS:
                    wanted.add((day, hour))
            counts = request.env['clinic.slot'].apply_week(
                doctor,
                local_to_utc(week_start.isoformat(), '00:00'),
                local_to_utc(week_end.isoformat(), '00:00'),
                [local_to_utc(day, hour) for day, hour in wanted],
            )
            created = counts['created']
            removed = counts['removed']
            skipped_past = counts['skipped_past']
        except (UserError, AccessError, ValidationError, ValueError) as err:
            return self._slot_redirect(role, week, doctor_id=doctor_id, error=self._user_error(err))
        message = _("%s créneau(x) ajouté(s), %s retiré(s).") % (created, removed)
        if skipped_past:
            message = "%s %s" % (message, _("Les heures déjà passées ont été ignorées."))
        return self._slot_redirect(role, week, doctor_id=doctor.id, message=message)

    @http.route('/clinic/creneaux/ajouter', type='http', auth='public', methods=['POST'], sitemap=False)
    def slots_add(self, **kw):
        role = self._gate(('receptionist',), allow_backend=True)
        if not isinstance(role, str):
            return role
        week = kw.get('week') or ''
        try:
            doctor = request.env['clinic.doctor'].browse(int(kw.get('doctor_id'))).exists()
            if not doctor or not doctor.active:
                raise UserError(_("Choisissez un médecin."))
            start = local_to_utc(kw.get('day'), kw.get('start_hour'))
            stop = local_to_utc(kw.get('day'), kw.get('stop_hour'))
            if stop <= start:
                raise UserError(_("L'heure de fin doit être après l'heure de début."))
            request.env['clinic.slot'].create({
                'doctor_id': doctor.id,
                'start': start,
                'stop': stop,
            })
        except (UserError, AccessError, ValidationError, ValueError) as err:
            return self._slot_redirect(role, week, doctor_id=kw.get('doctor_id'), error=self._user_error(err))
        return self._slot_redirect(role, week, doctor_id=doctor.id, message=_("Créneau ajouté."))

    @http.route('/clinic/creneaux/envoyer', type='http', auth='public', methods=['POST'], sitemap=False)
    def slots_send(self, **kw):
        role = self._gate(('receptionist',), allow_backend=True)
        if not isinstance(role, str):
            return role
        week = kw.get('week') or ''
        try:
            doctor = request.env['clinic.doctor'].browse(int(kw.get('doctor_id'))).exists()
            week_start, week_end = week_bounds(week)
            slots = request.env['clinic.slot'].search([
                ('doctor_id', '=', doctor.id),
                ('state', '=', 'draft'),
                ('start', '>=', local_to_utc(week_start.isoformat(), '00:00')),
                ('start', '<', local_to_utc(week_end.isoformat(), '00:00')),
            ])
            if not slots:
                raise UserError(_("Aucun créneau en brouillon pour cette semaine."))
            slots.action_send()
        except (UserError, AccessError, ValidationError, ValueError) as err:
            return self._slot_redirect(role, week, doctor_id=kw.get('doctor_id'), error=self._user_error(err))
        return self._slot_redirect(role, week, doctor_id=doctor.id, message=_("Créneaux envoyés au médecin."))

    @http.route('/clinic/creneaux/confirmer', type='http', auth='public', methods=['POST'], sitemap=False)
    def slots_confirm(self, **kw):
        role = self._gate(('doctor',))
        if not isinstance(role, str):
            return role
        week = kw.get('week') or ''
        try:
            profile = self._doctor_profile()
            slot = request.env['clinic.slot'].browse(int(kw.get('slot_id'))).exists()
            if not profile or not slot or slot.doctor_id != profile:
                raise UserError(_("Ce créneau ne vous est pas destiné."))
            slot.action_confirm()
        except (UserError, AccessError, ValidationError, ValueError) as err:
            if kw.get('next'):
                return self._back(role, kw.get('next'), error=self._user_error(err))
            return self._slot_redirect(role, week, error=self._user_error(err))
        if kw.get('next'):
            return self._back(role, kw.get('next'), message=_("Créneau confirmé."))
        return self._slot_redirect(role, week, message=_("Créneau confirmé."))

    @http.route('/clinic/creneaux/modifier', type='http', auth='public', methods=['POST'], sitemap=False)
    def slots_update(self, **kw):
        role = self._gate(('doctor',))
        if not isinstance(role, str):
            return role
        week = kw.get('week') or ''
        try:
            profile = self._doctor_profile()
            slot = request.env['clinic.slot'].browse(int(kw.get('slot_id'))).exists()
            if not profile or not slot or slot.doctor_id != profile:
                raise UserError(_("Ce créneau ne vous est pas destiné."))
            slot.update_times(
                local_to_utc(kw.get('day'), kw.get('start_hour')),
                local_to_utc(kw.get('day'), kw.get('stop_hour')),
            )
        except (UserError, AccessError, ValidationError, ValueError) as err:
            return self._slot_redirect(role, week, error=self._user_error(err))
        return self._slot_redirect(role, week, message=_("Créneau modifié."))

