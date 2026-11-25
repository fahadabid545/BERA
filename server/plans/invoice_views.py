from rest_framework.response import Response

from signin.company_views import CompanyObjectView

from .billing_details import get_details, save_details, shown
from .invoice_serializers import BillingDetailsSerializer, InvoiceLinkSerializer
from .invoices import link_for, list_invoices
from .models import BillingDetails, Invoice


class BillingDetailsView(CompanyObjectView):
    """The signed-in owner's own company only. Nobody else sees the details, the tax number
    included."""

    queryset = BillingDetails.objects.all()
    required_action = "billing.pay"
    serializer_class = BillingDetailsSerializer

    def get(self, request):
        self.get_queryset()  # checks the role and the company
        return Response(shown(get_details(request.user.company_id)))

    def put(self, request):
        self.get_queryset()
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        save_details(request.user.company_id, body.validated_data, by=request.user)
        return Response(shown(get_details(request.user.company_id)))


class InvoiceListView(CompanyObjectView):
    queryset = Invoice.objects.all()
    required_action = "billing.view"

    def get(self, request):
        self.get_queryset()
        return Response({"invoices": list_invoices(request.user.company_id)})


class InvoiceLinkView(CompanyObjectView):
    """The provider's address of one invoice, after the owner check and only for the company's
    own invoice (another company's id is simply not found). Never cached."""

    queryset = Invoice.objects.all()
    required_action = "billing.view"
    serializer_class = InvoiceLinkSerializer

    def get(self, request, id):
        query = self.get_serializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        invoice = self.get_object()
        reply = Response({"url": link_for(invoice, query.validated_data["kind"])})
        reply["Cache-Control"] = "no-store"
        return reply
