# payments/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PaymentViewSet

router = DefaultRouter()
router.register(r'payments', PaymentViewSet, basename='payment')

urlpatterns = [
    path('', include(router.urls)),
    
    # Add custom actions that need to be accessible
    path('payments/withdrawal-webhook/', PaymentViewSet.as_view({'post': 'withdrawal_webhook'}), name='withdrawal-webhook'),
    path('payments/sync_payment/', PaymentViewSet.as_view({'post': 'sync_payment'}), name='sync-payment'),
    path('payments/status_by_reference/', PaymentViewSet.as_view({'get': 'status_by_reference'}), name='status-by-reference'),
    path('payments/check_and_update_wallet/', PaymentViewSet.as_view({'get': 'check_and_update_wallet'}), name='check-update-wallet'),
    path('payments/test_confirm_payment/', PaymentViewSet.as_view({'post': 'test_confirm_payment'}), name='test-confirm-payment'),
    path('payments/webhook/', PaymentViewSet.as_view({'post': 'webhook'}), name='payment-webhook'),
    path('payments/initiate/', PaymentViewSet.as_view({'post': 'initiate'}), name='initiate-payment'),
    path('payments/initiate_simple/', PaymentViewSet.as_view({'post': 'initiate_simple'}), name='initiate-simple-payment'),
    path('payments/verify/', PaymentViewSet.as_view({'post': 'verify'}), name='verify-payment'),
    path('payments/my_payments/', PaymentViewSet.as_view({'get': 'my_payments'}), name='my-payments'),
    path('check-status/', PaymentViewSet.as_view({'get': 'check_status'}), name='check-status'),
]