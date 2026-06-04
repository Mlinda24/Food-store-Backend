# payments/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PaymentViewSet, payment_callback
from . import views

router = DefaultRouter()
router.register(r'payments', views.PaymentViewSet, basename='payment')

urlpatterns = [
    path('', include(router.urls)),
    # These must be standalone — router doesn't apply AllowAny correctly
    path('payments/callback/', views.payment_callback, name='payment-callback'),
    path('payments/webhook/', views.PaymentViewSet.as_view({'post': 'webhook'}), name='payment-webhook'),
    path('payments/withdrawal-webhook/', PaymentViewSet.as_view({'post': 'withdrawal_webhook'}), name='withdrawal-webhook'),
    path('payments/sync_payment/', PaymentViewSet.as_view({'post': 'sync_payment'}), name='sync-payment'),
    path('payments/status_by_reference/', PaymentViewSet.as_view({'get': 'status_by_reference'}), name='status-by-reference'),
    path('payments/test_confirm_payment/', PaymentViewSet.as_view({'post': 'test_confirm_payment'}), name='test-confirm-payment'),
    path('payments/initiate/', PaymentViewSet.as_view({'post': 'initiate'}), name='initiate-payment'),
    path('payments/initiate_simple/', PaymentViewSet.as_view({'post': 'initiate_simple'}), name='initiate-simple-payment'),
    path('payments/my_payments/', PaymentViewSet.as_view({'get': 'my_payments'}), name='my-payments'),
]