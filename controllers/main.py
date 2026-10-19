from odoo import http
from odoo.http import request


class LabResultsController(http.Controller):

    @http.route(
        '/lab/results/<int:request_id>',
        type='http',
        auth='public',
        website=True,
    )
    def view_lab_results(self, request_id, access_token=None, **kwargs):
        lab_req = (
            request.env['clinic.lab.request'].sudo().browse(request_id)
        )
        if not lab_req.exists() or lab_req.access_token != access_token:
            return request.not_found()

        return request.render(
            'medicalclinic.portal_lab_results_template',
            {
                'lab_request': lab_req,
            },
        )