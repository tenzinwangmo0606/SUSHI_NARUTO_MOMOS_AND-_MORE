from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # ----------- Public Routes -----------
    path('', views.home, name='home'),
    path('menu/', views.menu, name='menu'),
    path('contact/', views.contact, name='contact'),
    path('reservation/', views.table_reservation, name='reservation'),
    path('order/', views.order_menu, name='order_menu'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),

    # ----------- Admin Routes -----------
    path('admin2/', views.admin2_login, name='admin2_login'),
    path('admin2/dashboard/', views.admin2_dashboard, name='admin2_dashboard'),
    path('dashboard/login/', views.admin_login, name='admin_login'),

    # --- Menu Items ---
    path('menuitems/', views.menuitem_list, name='menuitem_list'),
    path('menuitems/add/', views.menuitem_add, name='menuitem_add'),
    path('menuitems/<int:pk>/view/', views.menuitem_view, name='menuitem_view'),
    path('menuitems/<int:pk>/edit/', views.menuitem_edit, name='menuitem_edit'),
    path('menuitems/<int:pk>/update/', views.menuitem_update, name='menuitem_update'),
    path('menuitems/<int:pk>/delete/', views.menuitem_delete, name='menuitem_delete'),

    # --- Categories ---
    path('category/create/', views.category_create, name='category_create'),
    path('category/<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('category/<int:pk>/delete/', views.category_delete, name='category_delete'),

    # --- Special Menu ---
    path('special_menu/', views.special_menu, name='special_menu'),
    path('special_menu/update/<int:pk>/', views.special_menu, name='special_menu_update'),
    path('special_menu/delete/<int:pk>/', views.special_menu_delete, name='special_menu_delete'),

    # --- Orders ---
    path('order/manage_history/', views.manage_order_history, name='manage_order_history'),
    path('order/food_table/', views.order_food_table, name='order_food_table'),
    path('order/history/', views.order_history, name='order_history'),
    path('order/delete/<int:pk>/', views.delete_order, name='delete_order'),
    path('order/live/', views.order_live, name='order_live'),
    path('order/update_status/<int:pk>/', views.update_order_status, name='update_order_status'),
    path('order/live-track/', views.order_live_track, name='order_live_track'),
    path('order/details/', views.order_details, name='order_details'),
    path('order/submit/', views.order_submit, name='order_submit'),
    path('order/<int:order_id>/action/', views.order_action, name='order_action'),
    path('order/cards/', views.order_card_list, name='order_card_list'),
    path('order/cards/<int:pk>/', views.order_card_detail, name='order_card_detail'),
    path('order/admin_action/<int:order_id>/', views.order_action_admin, name='order_action_admin'),

    # --- API ---
    path('api/search_menu_items/', views.search_menu_items_api, name='search_menu_items_api'),
    path('api/dashboard/metrics/', views.dashboard_metrics, name='dashboard_metrics'),
    path('api/dashboard/data/', views.dashboard_data, name='dashboard_data'),

    # --- Dashboard ---
    path('dashboard/', views.dashboard, name='dashboard'),
    path('cart/', views.cart_page, name='cart'),

    # --- Admin 2 Routes ---
    path('admin2/contacts/', views.admin_contact_list, name='admin_contact_list'),
    path('admin2/contacts/<int:pk>/', views.admin_contact_detail, name='admin_contact_detail'),
    path('admin2/contacts/<int:pk>/delete/', views.admin_contact_delete, name='admin_contact_delete'),
    path('admin2/reservations/', views.admin_reservations, name='admin_reservations'),
    path('admin2/reservations/<int:pk>/update-status/', views.update_reservation_status, name='update_reservation_status'),
    path('admin2/reservations/<int:pk>/view/', views.view_reservation, name='view_reservation'),
    path('admin2/reservations/<int:pk>/delete/', views.delete_reservation, name='delete_reservation'),
    path('admin2/reservations/<int:pk>/send-email/<str:mail_type>/', views.send_confirmation_email, name='send_confirmation_email'),
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('send-order-emails/', views.send_order_emails, name='send_order_emails'),

    # --- Static Pages ---
    path('privacy/', views.privacy_view, name='privacy'),
    path('terms/', views.terms_view, name='terms'),
    path('cookies/', views.cookies_view, name='cookies'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)