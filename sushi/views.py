from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.core.mail import send_mail, BadHeaderError
from django.contrib import messages
from django.utils import timezone
from django.db.models import Prefetch
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count, F, ExpressionWrapper, DecimalField
import json
from django.urls import reverse
from django.conf import settings
import logging
import os
import requests

from django.http import HttpResponse
from django.conf import settings
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

from .models import MenuCategory, MenuItem, SpecialMenu, Order, CustomUser, Contact, TableReservation
from .forms import MenuItemForm, SpecialMenuForm
from django.db.models import Q
from datetime import timedelta

logger = logging.getLogger(__name__)

def send_new_email(to, cc=[], bcc=[], subject="", content=""):
    """Send email via Brevo API"""
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = settings.BREVO_API_KEY

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )
    sender = {"name": "SUSHI NARUTO MOMOS", "email": settings.DEFAULT_FROM_EMAIL}

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=to,
        html_content=content,
        sender=sender,
        subject=subject,
    )
    api_response = api_instance.send_transac_email(send_smtp_email)
    return True

# ---------------- Public Views ----------------

def home(request):
    featured_menuitems = MenuItem.objects.filter(featured=True)[:6]
    special_menuitems = SpecialMenu.objects.all()[:6]
    return render(request, 'home.html', {
        'featured_menuitems': featured_menuitems,
        'special_menuitems': special_menuitems
    })

def menu(request):
    # Use Categories as the primary source and prefetch their MenuItems ordered by name.
    # This guarantees each category block contains exactly the items saved under that category.
 
    categories = MenuCategory.objects.prefetch_related(
        Prefetch('menuitem_set', queryset=MenuItem.objects.order_by('name'))
    ).all()  # Remove order_by('name') to preserve database order of categories

    # Keep menuitems if other code expects it
    menuitems = MenuItem.objects.select_related('category').order_by('category__name', 'name').all()
    return render(request, 'menu.html', {'menuitems': menuitems, 'categories': categories})

def contact(request):
    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        email = (request.POST.get('email') or '').strip()
        message = (request.POST.get('message') or '').strip()

        # Basic validation
        if not email:
            messages.error(request, 'Please provide a valid email address.')
            return redirect('contact')

        # Save to DB (safe guard)
        try:
            Contact.objects.create(name=name or 'Anonymous', email=email, message=message)
        except Exception as e:
            logging.exception("Failed to save contact message")
            messages.error(request, 'Failed to save your message. Please try again later.')
            return redirect('contact')

        subject = f'New message from {name or "Anonymous"}'
        full_message = f"From: {name} <{email}>\n\nMessage:\n{message}"

        # Use configured DEFAULT_FROM_EMAIL as sender, and notify site owner(s)
        try:
            send_mail(subject, full_message, settings.DEFAULT_FROM_EMAIL, [settings.EMAIL_HOST_USER])
            messages.success(request, 'Message sent successfully!')
        except Exception as e:
            logging.exception("Failed to send contact notification email")
            # Still treat as saved; inform user that email failed
            messages.success(request, 'Message saved. Notification email could not be sent at this time.')

        return redirect('contact')

    return render(request, 'contact.html')

def table_reservation(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        # Ensure phone is never None (prevent DB NOT NULL errors)
        phone = request.POST.get('phone') or ''
        date = request.POST.get('date')
        time = request.POST.get('time')
        # accept either 'guests' or legacy 'people' field
        guests = request.POST.get('guests') or request.POST.get('people') or 1
        special_requests = request.POST.get('special_requests', '')

        # Basic validation could be extended; here we save the reservation
        TableReservation.objects.create(
            name=name or 'Guest',
            email=email or '',
            phone=phone,
            date=date,
            time=time,
            guests=int(guests) if str(guests).isdigit() else 1,
            special_requests=special_requests
        )

        # optional: send confirmation email (best-effort) only if email provided
        if email:
            try:
                send_mail(
                    'Reservation received',
                    f'Thank you {name}, your reservation for {date} at {time} has been received.',
                    'no-reply@example.com',
                    [email]
                )
            except Exception:
                pass

        messages.success(request, 'Reservation submitted. We will contact you to confirm.')
        # Redirect to the correct URL name and include success flag for template
        return redirect(reverse('reservation') + '?success=1')

    # On GET, show reservation_success if query param present
    reservation_success = request.GET.get('success') == '1'
    return render(request, 'reservation.html', {'reservation_success': reservation_success})

def order_menu(request):
    return render(request, 'order_menu.html')

# ---------------- Public Login & Signup ----------------

def login_view(request):
    if request.method == 'POST':
        identifier = request.POST.get('identifier')
        password = request.POST.get('password')
        user = None
        try:
            user_obj = CustomUser.objects.get(Q(username=identifier) | Q(email=identifier))
            user = authenticate(request, username=user_obj.username, password=password)
        except CustomUser.DoesNotExist:
            user = None
        if user is not None:
            auth_login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'login.html', {'login_error': 'Invalid username/email or password.'})
    return render(request, 'login.html')

def signup_view(request):
    # Customer signup (uses base.html)
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        if password != confirm_password:
            return render(request, 'login.html', {'signup_error': 'Passwords do not match'})
        if CustomUser.objects.filter(email=email).exists():
            return render(request, 'login.html', {'signup_error': 'Email already exists'})
        if CustomUser.objects.filter(username=username).exists():
            return render(request, 'login.html', {'signup_error': 'Username already exists'})
        user = CustomUser.objects.create_user(email=email, username=username, password=password)
        auth_login(request, user)
        return redirect('dashboard')
    return render(request, 'login.html')

def logout_view(request):
    auth_logout(request)
    return redirect('login')

@login_required
def dashboard(request):
    # Customer dashboard (uses base.html)
    return render(request, 'dashboard.html', {'user': request.user})

# ---------------- Admin Login ----------------

def admin_login(request):
    # Admin login (uses base2.html)
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('menuitem_list')

    error = None
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_staff:
            auth_login(request, user)
            return redirect('menuitem_list')
        else:
            error = "Invalid credentials or user does not have access."

    return render(request, "admin/login.html", {"error": error})

# ---------------- Admin2 Login ----------------

def admin2_login(request):
    if request.user.is_authenticated and getattr(request.user, "user_type", None) == "management":
        return redirect('admin2_dashboard')
    error = None
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        # Check user exists, is active, and is management type
        if user is not None and getattr(user, "user_type", None) == 'management' and user.is_active:
            auth_login(request, user)
            return redirect('admin2_dashboard')
        else:
            error = "Invalid username/password or not authorized."
    return render(request, "admin2/admin2_login.html", {"error": error})

def admin2_dashboard(request):
    if not request.user.is_authenticated or getattr(request.user, "user_type", None) != "management":
        return redirect('admin2_login')
    return render(request, 'admin2/admin2.html')

# ---------------- Admin Menu Management ----------------
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import MenuItem, MenuCategory

# ---------------- MenuItem Management ----------------

def menuitem_list(request):
    from collections import defaultdict
    from django.core.files.images import get_image_dimensions
    from django.core.exceptions import ValidationError
    menuitems = MenuItem.objects.select_related('category').all()
    menuitems_by_category = defaultdict(list)
    for item in menuitems:
        menuitems_by_category[item.category].append(item)
    categories = MenuCategory.objects.all()

    error_message = None

    if request.method == 'POST':
        form = MenuItemForm(request.POST, request.FILES)
        if 'image' in request.FILES:
            image_file = request.FILES['image']
            try:
                # Try to get image dimensions to validate image
                get_image_dimensions(image_file)
            except Exception:
                form.add_error('image', 'Upload a valid image. The file you uploaded was either not an image or a corrupted image.')
        if form.is_valid():
            form.save()
            return redirect('menuitem_list')
        else:
            # If image error, show error message
            if form.errors.get('image'):
                error_message = form.errors['image']
    else:
        form = MenuItemForm()

    return render(request, 'admin2/menuitem_list.html', {
        'menuitems_by_category': dict(menuitems_by_category),
        'categories': categories,
        'form': form,
        'error_message': error_message
    })

def menuitem_create(request):
    categories = MenuCategory.objects.all()
    if request.method == 'POST':
        category_id = request.POST.get('category')
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        price = request.POST.get('price')
        image = request.FILES.get('image')
        try:
            category = MenuCategory.objects.get(id=category_id)
            MenuItem.objects.create(category=category, name=name, description=description, price=price, image=image)
            return redirect('menuitem_list')
        except MenuCategory.DoesNotExist:
            error_message = "Selected category does not exist."
            return render(request, 'admin/menuitem_form.html', {'categories': categories, 'error_message': error_message})
    return render(request, 'admin/menuitem_form.html', {'categories': categories})

def menuitem_edit(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id)
    categories = MenuCategory.objects.all()
    if request.method == 'POST':
        item.name = request.POST.get('name')
        item.description = request.POST.get('description')
        item.price = request.POST.get('price')
        item.category = get_object_or_404(MenuCategory, id=request.POST.get('category'))
        if 'image' in request.FILES:
            item.image = request.FILES['image']
        item.save()
        return redirect('menuitem_list')
    return render(request, 'admin/menuitem_form.html', {'item': item, 'categories': categories})

def menuitem_delete(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    if request.method == 'POST':
        item.delete()
        return redirect('menuitem_list')
    return render(request, 'admin2/menuitem_confirm_delete.html', {'item': item})

# ---------------- Special Menu Management ----------------

@login_required
def special_menu(request, pk=None):
    if not request.user.is_staff:
        return redirect('admin_login')

    if pk:
        item = get_object_or_404(SpecialMenu, pk=pk)
    else:
        item = None

    if request.method == 'POST':
        form = SpecialMenuForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            return redirect('special_menu')
    else:
        form = SpecialMenuForm(instance=item)

    special_menu_items = SpecialMenu.objects.all()
    return render(request, 'admin2/special_menu.html', {
        'form': form,
        'item': item,
        'special_menu_items': special_menu_items
    })

@login_required
def special_menu_delete(request, pk):
    if not request.user.is_staff:
        return redirect('admin_login')
    item = get_object_or_404(SpecialMenu, pk=pk)
    item.delete()
    return redirect('special_menu')

@login_required
def special_menu_update(request, pk):
    if not request.user.is_staff:
        return redirect('admin_login')
    item = get_object_or_404(SpecialMenu, pk=pk)
    if request.method == 'POST':
        form = SpecialMenuForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            return redirect('special_menu')
    else:
        form = SpecialMenuForm(instance=item)
    special_menu_items = SpecialMenu.objects.all()
    return render(request, 'admin2/special_menu.html', {
        'form': form,
        'item': item,
        'special_menu_items': special_menu_items
    })

# ---------------- Category Management ----------------

@csrf_exempt
def category_create(request):
    if request.method == 'POST':
        # Accept both AJAX and regular POST
        category_name = request.POST.get('category_name') or request.POST.get('name')
        username = request.POST.get('username') or request.POST.get('added_by', 'admin')
        if category_name:
            MenuCategory.objects.create(name=category_name, added_by=username)
            # If AJAX, return JSON
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            # Otherwise, redirect back
            return redirect(request.META.get('HTTP_REFERER', '/'))
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Missing fields'})
        return redirect(request.META.get('HTTP_REFERER', '/'))
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'Invalid request'})
    return redirect(request.META.get('HTTP_REFERER', '/'))

def category_edit(request, pk):
    category = get_object_or_404(MenuCategory, pk=pk)
    if request.method == 'POST':
        category.name = request.POST.get('name')
        category.added_by = request.POST.get('added_by', 'admin')
        category.save()
        return redirect('menuitem_list')
    return render(request, 'menu_management.html', {'category': category})

def category_delete(request, pk):
    category = get_object_or_404(MenuCategory, pk=pk)
    category.delete()
    return redirect('menuitem_list')
# ---------------- Menu Item Details / Add / Update ----------------

def menuitem_view(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    return render(request, 'admin2/menuitem_view.html', {'item': item})

def menuitem_add(request):
    if request.method == 'POST':
        form = MenuItemForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('menuitem_list')
    else:
        form = MenuItemForm()
    return render(request, 'admin2/menuitem_add.html', {'form': form})

def menuitem_update(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    if request.method == 'POST':
        form = MenuItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            return redirect('menuitem_list')
    else:
        form = MenuItemForm(instance=item)
    return render(request, 'admin2/menuitem_add.html', {'form': form})

# ---------------- Order Processing ----------------
@csrf_exempt
def order_submit(request):
    """
    Accepts both JSON (AJAX) and regular form POSTs.
    Supports:
      - cart: [ {name, price, qty}, ... ]  (JSON array)
      - single item: item, price, qty, mobile, address, delivery, orderType
    For guest users, an 'email' field is required.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    data = {}
    try:
        body = request.body.decode('utf-8') or '{}'
        data = json.loads(body)
    except Exception:
        data = request.POST.dict()

    email = data.get('email') or request.POST.get('email')
    if not email:
        return JsonResponse({'success': False, 'error': 'Email required'}, status=400)

    cart = data.get('cart')
    created_ids = []

    def _num(v, default=0):
        try:
            return float(v)
        except Exception:
            return default

    # CART FLOW
    if cart and isinstance(cart, list):
        mobile = data.get('mobile')
        address = data.get('address')
        delivery = data.get('delivery')

        order_type = data.get('orderType') or 'now'
        order_date = data.get('orderDate') if order_type == 'later' else None
        order_time = data.get('orderTime') if order_type == 'later' else None

        if not (mobile and address and delivery):
            return JsonResponse({'success': False, 'error': 'Missing mobile/address/delivery'}, status=400)

        for c in cart:
            name = c.get('name') or c.get('item')
            price = _num(c.get('price'))
            qty = int(c.get('qty') or 1)
            order = Order.objects.create(
                item=name,
                price=price,
                qty=qty,
                email=email,
                mobile=mobile,
                address=address,
                delivery=delivery,
                order_type=order_type,
                order_date=order_date,
                order_time=order_time
            )
            created_ids.append(order.id)

    # SINGLE ITEM FLOW
    else:
        item = data.get('item') or request.POST.get('item')
        price = _num(data.get('price') or request.POST.get('price'))
        qty = int(data.get('qty') or request.POST.get('qty') or 1)
        mobile = data.get('mobile') or request.POST.get('mobile')
        address = data.get('address') or request.POST.get('address')
        delivery = data.get('delivery') or request.POST.get('delivery')

        order_type = data.get('orderType') or request.POST.get('orderType') or 'now'
        order_date = data.get('orderDate') if order_type == 'later' else None
        order_time = data.get('orderTime') if order_type == 'later' else None

        if not all([item, mobile, address, delivery]):
            return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)

        order = Order.objects.create(
            item=item,
            price=price,
            qty=qty,
            email=email,
            mobile=mobile,
            address=address,
            delivery=delivery,
            order_type=order_type,
            order_date=order_date,
            order_time=order_time,
        )
        created_ids.append(order.id)

    # Prepare order summary and send emails (best-effort)
    order_details_str = ""
    total_price = 0.0

    if cart and isinstance(cart, list):
        for c in cart:
            name = c.get('name') or c.get('item')
            price = _num(c.get('price'))
            qty = int(c.get('qty') or 1)
            item_total = price * qty
            total_price += item_total
            order_details_str += f"- {name} (x{qty}) : {item_total:.2f} CHF\n"
    else:
        item_total = price * qty
        total_price = item_total
        order_details_str = f"- {item} (x{qty}) : {item_total:.2f} CHF\n"

    message = f"""
    <html>
    <body style="font-family: Arial; padding:20px; background:#f4f4f4;">
        <div style="max-width:600px; margin:auto; background:white; padding:20px; border-radius:8px;">
            <h2 style="text-align:center;">New Order Received</h2>
            <h3>Customer Details</h3>
            <div style="background:#f9f9f9; padding:10px; border-radius:6px;">
                <p><strong>Email:</strong> {email}</p>
                <p><strong>Mobile:</strong> {data.get('mobile')}</p>
                <p><strong>Address:</strong> {data.get('address')}</p>
            </div>
            <h3 style="margin-top:20px;">Order Details</h3>
            <div style="background:#f9f9f9; padding:10px; border-radius:6px; white-space:pre-line;">
                {order_details_str}
            </div>
            <p><strong>Total Price: {total_price:.2f} CHF</strong></p>
            <h3>Delivery Information</h3>
            <div style="background:#f9f9f9; padding:10px; border-radius:6px;">
                <p><strong>Delivery Method:</strong> {data.get('delivery')}</p>
                <p><strong>Order Type:</strong> {data.get('orderType')}</p>
            </div>
            {f"<p><strong>Scheduled:</strong> {data.get('orderDate')} at {data.get('orderTime')}</p>" if data.get('orderType') == 'later' else ""}
        </div>
    </body>
    </html>
    """

    try:
        manager = [{"email": "info.sushinaruto@gmail.com"}]
        send_new_email(to=manager, subject="New Order Received", content=message)
        customer = [{"email": email}]
        send_new_email(to=customer, subject="Your Order Confirmation - Sushi Naruto", content=message)
    except Exception:
        logger.exception("Email Sending Error")

    return JsonResponse({'success': True, 'order_ids': created_ids})

@login_required
def order_action(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id, email=request.user.email)

        if request.method == 'POST':
            action = request.POST.get('action')

            if action == 'get':
                order.status = 'got'
            elif action == 'out':
                order.status = 'out'
            elif action == 'cancel':
                order.status = 'cancelled'

            order.save()

        return redirect('order_details')

    except Exception as e:
        logging.exception("Error in order_action")
        return redirect('order_details')

@login_required
def order_action_admin(request, order_id=None):
    try:
        if not request.user.is_staff and getattr(request.user, "user_type", None) != "management":
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)
            return redirect('admin2_login')

        if request.method == 'POST':
            action = request.POST.get('action')
            reason = request.POST.get('reason', '')
            
            # Handle bulk orders from POST or single order from URL
            order_ids = request.POST.getlist('order_ids')
            if not order_ids and order_id:
                order_ids = [order_id]
            
            if not order_ids:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': 'No orders selected'}, status=400)
                messages.error(request, 'No orders selected')
                return redirect('order_food_table')
            
            # Fetch all orders to update
            orders = Order.objects.filter(id__in=order_ids)
            if not orders.exists():
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': 'Orders not found'}, status=404)
                messages.error(request, 'Orders not found')
                return redirect('order_food_table')
            
            # Determine new status based on action
            new_status = None
            subject = ""
             
            if action == "accept":
                subject = "Order Accepted"
                new_status = "Accepted"
            elif action == "making":
                subject = "Order Being Prepared"
                new_status = "Making"
            elif action == "collect":
                subject = "Order Ready to Collect"
                new_status = "Ready to Collect"
            elif action == "delivered":
                subject = "Order Delivered"
                new_status = "Delivered"
            elif action == "cancel":
                subject = "Order Cancelled"
                new_status = "Cancelled"
            else:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)
                return redirect('order_food_table')

            # Update all selected orders with new status
            for order in orders:
                order.status = new_status
                order.save()
                
                # Build personalized email for each order
                if action == "accept":
                    msg = "Good news! Your order has been accepted and will be prepared soon."
                elif action == "making":
                    msg = "Your order is currently being prepared by our chef."
                elif action == "collect":
                    msg = "Please come to the restaurant to collect your order."
                elif action == "delivered":
                    msg = "Enjoy your meal! Thank you for choosing us."
                elif action == "cancel":
                    msg = f"Reason: {reason}" if reason else "Your order has been cancelled."
                else:
                    msg = ""
                
                order_details = f"""
                <p><strong>Order ID:</strong> #{order.id}</p>
                <p><strong>Item:</strong> {order.item}</p>
                <p><strong>Quantity:</strong> {order.qty}</p>
                <p><strong>Price per item:</strong> {order.price} CHF</p>
                <p><strong>Total Price:</strong> {order.total_price} CHF</p>
                <p><strong>Delivery:</strong> {order.delivery}</p>
                <p><strong>Address:</strong> {order.address}</p>
                <p><strong>Mobile:</strong> {order.mobile}</p>
                """
                
                html_body = f"""
                <div style="font-family: Arial, sans-serif; padding: 20px; background: #f8f8f8;">
                    <div style="background: white; padding: 20px; border-radius: 10px; max-width: 600px; margin: auto;">
                        <h2 style="color: #d81b60; text-align:center;">Order Status Update</h2>
                        <p>{msg}</p>
                        <h3 style="margin-top: 20px;">Order Details</h3>
                        <div style="border: 1px solid #ddd; padding: 15px; border-radius: 6px; background:#fafafa;">
                            {order_details}
                        </div>
                        <p style="margin-top: 25px;">
                            Thank you for ordering with <strong>Sushi Naruto Momos</strong>.
                        </p>
                    </div>
                </div>
                """
                
                # Send email for this order
                try:
                    to = [{"email": order.email}]
                    send_new_email(to, subject=subject, content=html_body)
                except Exception as mail_error:
                    logger.exception(f"Mail send failed for order {order.id}: {mail_error}")

            pending_count = Order.objects.filter(status__in=['Accepted', 'Making']).count()

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f'{len(orders)} order(s) {action}ed successfully',
                    'new_status': new_status,
                    'pending_count': pending_count,
                })

            messages.success(request, f'{len(orders)} order(s) {action}ed successfully')
            return redirect('order_food_table')

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Invalid method'}, status=405)

        return redirect('order_food_table')

    except Exception as e:
        logging.exception("Error in order_action_admin")

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Server error'}, status=500)

        messages.error(request, "Something went wrong.")
        return redirect('order_food_table')

@login_required
def order_history(request):
    orders = Order.objects.filter(email=request.user.email).order_by('-created_at')
    return render(request, 'order_history.html', {'orders': orders})

@login_required
def order_detail(request, pk):
    try:
        if request.user.is_staff:
            order = get_object_or_404(Order, pk=pk)
        else:
            order = get_object_or_404(Order, pk=pk, email=request.user.email)

        try:
            menu_item = MenuItem.objects.get(name=order.item)
            item_image = menu_item.image
        except MenuItem.DoesNotExist:
            item_image = None

        context = {
            'order': order,
            'item_image': item_image,
            'status_class': get_status_class(order.status),
            'can_cancel': order.status in ['pending', 'Accepted'],
            'can_modify': request.user.is_staff,
            'active_tab': 'orders'
        }

        return render(request, 'order_detail.html', context)

    except Order.DoesNotExist:
        messages.error(request, 'Order not found.')
        return redirect('dashboard')

order_details = order_detail

@login_required
def order_live_track(request):
    orders = Order.objects.filter(email=request.user.email, status='pending').order_by('-created_at')
    return render(request, 'order_live_track.html', {'orders': orders})

@login_required
def order_track(request, pk):
    order = Order.objects.get(pk=pk, email=request.user.email)
    return render(request, 'order_track.html', {'order': order})

@login_required
def order_live(request):
    if not request.user.is_staff:
        return redirect('admin_login')

    pending_orders = Order.objects.filter(
        status__in=['pending', 'Accepted', 'Making', 'Ready to Collect']
    ).order_by('-created_at')

    orders_with_items = []
    for order in pending_orders:
        try:
            menu_item = MenuItem.objects.get(name=order.item)
            image = menu_item.image
        except MenuItem.DoesNotExist:
            image = None

        orders_with_items.append({
            'order': order,
            'image': image,
            'status_class': get_status_class(order.status),
            'created_at_formatted': order.created_at.strftime("%Y-%m-%d %H:%M:%S")
        })

    return render(request, 'admin2/order_live.html', {
        'orders_with_items': orders_with_items,
        'active_tab': 'live_orders'
    })

def get_status_class(status):
    status_classes = {
        'pending': 'bg-yellow-100 text-yellow-800',
        'Accepted': 'bg-blue-100 text-blue-800',
        'Making': 'bg-purple-100 text-purple-800',
        'Ready to Collect': 'bg-green-100 text-green-800',
        'Delivered': 'bg-gray-100 text-gray-800',
        'Cancelled': 'bg-red-100 text-red-800'
    }
    return status_classes.get(status, 'bg-gray-100 text-gray-800')

def order_food_table(request):
    if not request.user.is_staff:
        return redirect('admin_login')

    orders = Order.objects.exclude(
        status__in=['Delivered', 'Cancelled']
    ).order_by('-created_at')

    return render(request, 'admin2/order_food_table.html', {
        'orders': orders,
        'active_tab': 'food_orders'
    })

def manage_order_history(request):
    if not request.user.is_staff:
        return redirect('admin_login')

    status_filter = request.GET.get('status', '')
    date_filter = request.GET.get('date', '')

    orders = Order.objects.all()

    if status_filter:
        orders = orders.filter(status=status_filter)
    if date_filter:
        orders = orders.filter(created_at__date=date_filter)

    orders = orders.order_by('-created_at')

    all_statuses = Order.objects.values_list('status', flat=True).distinct()

    return render(request, 'admin2/manage_order_history.html', {
        'orders': orders,
        'all_statuses': all_statuses,
        'current_status': status_filter,
        'current_date': date_filter,
        'active_tab': 'order_history'
    })

@csrf_exempt
def search_menu_items_api(request):
    """
    Returns JSON list of menu items matching query.
    Each item includes: id, name, description, image_url, url (anchor to menu item id).
    """
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse([], safe=False)

    menu_items = MenuItem.objects.filter(
        Q(name__icontains=query) | Q(description__icontains=query)
    ).values('id', 'name', 'description', 'image')

    results = []
    for item in menu_items:
        image_url = f"{settings.MEDIA_URL}{item['image']}" if item['image'] else None
        results.append({
            'id': item['id'],
            'name': item['name'],
            'description': item['description'],
            'image_url': image_url,
            'url': f'#menu-item-{item["id"]}'
        })
    return JsonResponse(results, safe=False)

@login_required
def delete_order(request, pk):
    if not request.user.is_staff:
        return redirect('admin_login')
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        order.delete()
        return redirect('order_live')
    return render(request, 'order_confirm_delete.html', {'order': order})

@login_required
def update_order_status(request, pk):
    if not request.user.is_staff:
        return redirect('admin_login')

    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        status = request.POST.get('status')
        if status:
            order.status = status
            order.save()

            subject = f'Your order #{order.id} has been {status}'
            message = f'Hi, your order for {order.item} has been {status}.'
            try:
                send_mail(subject, message, 'saranvignesh55@gmail.com', [order.email])
                messages.success(request, f'Order #{order.id} updated to {status} and notification sent.')
            except Exception as e:
                messages.error(request, f'Order status updated, but failed to send notification. Error: {e}')

    return redirect('manage_order_history')

@login_required
def admin_manage(request):
    """
    Management landing page for admin2 users.
    Ensures only staff or management users can access the admin manage page.
    """
    if not request.user.is_authenticated or not (request.user.is_staff or getattr(request.user, "user_type", None) == "management"):
        return redirect('admin2_login')

    return render(request, 'admin2/adminmanage.html')

@login_required
def order_card_list(request):
    orders = Order.objects.filter(email=request.user.email).order_by('-created_at')
    return render(request, 'order_card_list.html', {'orders': orders})

@login_required
def order_card_detail(request, pk):
    order = get_object_or_404(Order, pk=pk, email=request.user.email)

    steps = ['pending', 'Accepted', 'Making', 'Ready to Collect', 'Delivered']

    try:
        current_step_index = steps.index(order.status)
    except ValueError:
        current_step_index = -1

    context = {
        'order': order,
        'steps': steps,
        'current_step_index': current_step_index,
    }
    return render(request, 'order_card_detail.html', context)

def cart_page(request):
    """
    Renders cart page. When coming from a successful order_submit (form), the
    created order ids are saved in session['last_order_ids'] and displayed here
    as last_orders (then removed from session).
    """
    last_orders = []
    last_ids = request.session.pop('last_order_ids', None)
    if last_ids:
        last_orders = list(Order.objects.filter(id__in=last_ids).order_by('-created_at'))
    return render(request, 'cart.html', {'last_orders': last_orders})

@login_required
def admin_contact_list(request):
    if not request.user.is_staff:
        return redirect('admin_login')

    contacts = Contact.objects.all().order_by('-created_at')
    return render(request, 'admin2/contact_list.html', {
        'contacts': contacts,
        'active_tab': 'contacts'
    })

@login_required
def admin_contact_detail(request, pk):
    if not request.user.is_staff:
        return redirect('admin_login')
    contact = get_object_or_404(Contact, pk=pk)
    return render(request, 'admin2/contact_detail.html', {
        'contact': contact,
        'active_tab': 'contacts'
    })

@login_required
def admin_contact_delete(request, pk):
    if not request.user.is_staff:
        return redirect('admin_login')
    contact = get_object_or_404(Contact, pk=pk)
    if request.method == 'POST':
        contact.delete()
        messages.success(request, 'Contact request deleted successfully.')
        return redirect('admin_contact_list')
    return render(request, 'admin2/contact_confirm_delete.html', {'contact': contact})

@login_required
def admin_reservations(request):
    if not request.user.is_staff:
        return redirect('admin_login')

    date_filter = request.GET.get('date')
    status_filter = request.GET.get('status')

    reservations = TableReservation.objects.all()
    if date_filter:
        reservations = reservations.filter(date=date_filter)
    if status_filter:
        reservations = reservations.filter(status=status_filter)

    reservations = reservations.order_by('date', 'time')

    return render(request, 'admin2/reservations.html', {
        'reservations': reservations,
        'active_tab': 'reservations'
    })

@login_required
def update_reservation_status(request, pk):
    if not request.user.is_staff:
        return redirect('admin_login')

    reservation = get_object_or_404(TableReservation, pk=pk)
    if request.method == 'POST':
        status = request.POST.get('status')
        if status in ['confirmed', 'cancelled']:
            reservation.status = status
            reservation.save()

            subject = f'Your table reservation for {reservation.date} has been {status}'
            message = f'Dear {reservation.name},\n\nYour table reservation for {reservation.date} at {reservation.time} has been {status}.'
            try:
                send_mail(subject, message, 'saranvignesh55@gmail.com', [reservation.email])
            except Exception as e:
                messages.error(request, f'Status updated but failed to send notification: {str(e)}')

    return redirect('admin_reservations')

@login_required
def send_confirmation_email(request, pk, mail_type):
    if not request.user.is_staff:
        return redirect('admin_login')

    reservation = get_object_or_404(TableReservation, pk=pk)

    if mail_type == 'confirmed':
        subject = f'Your table reservation for {reservation.date} is confirmed'
        message = f'Dear {reservation.name},\n\nYour table reservation for {reservation.date} at {reservation.time} has been confirmed.'
    elif mail_type == 'cancelled':
        subject = f'Your table reservation for {reservation.date} is cancelled'
        message = f'Dear {reservation.name},\n\nWe regret to inform you that your table reservation for {reservation.date} at {reservation.time} has been cancelled.'
    else:
        messages.error(request, 'Invalid email type.')
        return redirect('admin_reservations')

    try:
        send_mail(subject, message, 'saranvignesh55@gmail.com', [reservation.email])
        messages.success(request, f'{mail_type.capitalize()} email sent to {reservation.email}.')
    except Exception as e:
        messages.error(request, f'Failed to send {mail_type} email: {str(e)}')

    return redirect('admin_reservations')

@login_required
def view_reservation(request, pk):
    if not request.user.is_staff:
        return redirect('admin_login')
    reservation = get_object_or_404(TableReservation, pk=pk)
    return render(request, 'admin2/reservation_view.html', {
        'reservation': reservation,
        'active_tab': 'reservations'
    })

@login_required
def delete_reservation(request, pk):
    if not request.user.is_staff:
        return redirect('admin_login')
    reservation = get_object_or_404(TableReservation, pk=pk)
    if request.method == 'POST':
        reservation.delete()
        messages.success(request, 'Reservation deleted successfully.')
        return redirect('admin_reservations')
    return render(request, 'admin2/reservation_confirm_delete.html', {'reservation': reservation})

# ---------------- Admin Dashboard ----------------

@login_required
def admin_dashboard(request):
    # Get base order summary
    order_summary = Order.dashboard_summary()
    
    # Enhance order summary with more details
    order_summary.update({
        'recent_orders': [
            {
                'id': order.id,
                'customer_name': order.email.split('@')[0],
                'item': order.item,
                'total_amount': float(order.total_price),
                'status': order.status.title(),
                'created_at': order.created_at,
                'order_type': order.order_type,
                'delivery': order.delivery
            }
            for order in Order.objects.order_by('-created_at')[:10]
        ]
    })

    # Get detailed top products with sales count and revenue
    top_products = MenuItem.objects.annotate(
        sales_count=Count('order'),
        revenue=Sum(
            ExpressionWrapper(
                F('price') * F('order__qty'),
                output_field=DecimalField()
            )
        )
    ).filter(sales_count__gt=0).order_by('-sales_count')[:5]

    top_products_data = [{
        'name': product.name,
        'sales': product.sales_count,
        'revenue': float(product.revenue or 0),
        'category': product.category.name
    } for product in top_products]

    # Get recent feedback with user details
    recent_feedback = Contact.objects.select_related('email').filter(
        created_at__gte=timezone.now() - timedelta(days=30)
    ).order_by('-created_at')[:5]

    feedback_data = [{
        'message': fb.message,
        'user_name': fb.name,
        'date': fb.created_at,
        'status': fb.status
    } for fb in recent_feedback]

    # Get active users and their activities
    active_users = CustomUser.objects.filter(
        is_active=True,
        last_login__gte=timezone.now() - timedelta(minutes=15)
    ).select_related('user_type')

    user_activities = []
    for user in active_users:
        recent_orders = Order.objects.filter(
            email=user.email,
            created_at__gte=timezone.now() - timedelta(days=1)
        ).count()
        
        user_activities.append({
            'user': user,
            'action': f"Placed {recent_orders} orders recently" if recent_orders else "Browsing",
            'timestamp': user.last_login,
            'is_online': True,
            'type': user.user_type
        })

    # Get table reservations
    recent_reservations = TableReservation.objects.filter(
        date__gte=timezone.now().date()
    ).order_by('date', 'time')[:5]

    reservation_data = [{
        'name': res.name,
        'date': res.date,
        'time': res.time,
        'guests': res.guests,
        'status': res.status
    } for res in recent_reservations]

    context = {
        'order_summary': order_summary,
        'top_products': top_products_data,
        'recent_feedback': feedback_data,
        'user_logs': user_activities,
        'online_users_count': len(user_activities),
        'recent_reservations': reservation_data,
        
        # Debug info
        'total_orders_count': Order.objects.count(),
        'total_users_count': CustomUser.objects.count(),
        'total_revenue': Order.objects.aggregate(
            total=Sum(ExpressionWrapper(
                F('price') * F('qty'),
                output_field=DecimalField()
            )))['total'] or 0,
        'debug_info': {
            'last_update': timezone.now(),
            'active_users': active_users.count(),
            'pending_orders': Order.objects.filter(status='pending').count()
        }
    }

    return render(request, 'admin2/adminmanage.html', context)

@login_required
@require_http_methods(["GET"])
def dashboard_metrics(request):
    try:
        # Get order summary
        order_summary = Order.dashboard_summary()
        
        # Add CSRF token to response for security
        return JsonResponse({
            'status': 'success',
            'data': order_summary
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@login_required
@require_http_methods(["GET"])
def dashboard_data(request):
    try:
        # Prepare timestamp for active users
        active_threshold = timezone.now() - timezone.timedelta(minutes=15)
        
        data = {
            'orders': list(Order.objects.values(
                'id', 'item', 'price', 'qty', 'status', 'created_at', 'email'
            ).order_by('-created_at')[:10]),
            
            'top_products': list(MenuItem.objects.annotate(
                sales=Count('order')
            ).values('name', 'sales')
            .filter(sales__gt=0)
            .order_by('-sales')[:5]),
            
            'feedback': list(Contact.objects.values(
                'name', 'message', 'created_at', 'status'
            ).order_by('-created_at')[:5]),
            
            'active_users': list(CustomUser.objects.filter(
                is_active=True,
                last_login__gte=active_threshold
            ).values('username', 'last_login', 'email'))
        }

        return JsonResponse({
            'status': 'success',
            'data': data
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@require_http_methods(["POST"])
def send_order_emails(request):
    """
    API endpoint to send order confirmation emails.
    Called from cart.html after successful order placement.
    """
    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        customer_email = data.get('customer_email')

        if not order_id or not customer_email:
            return JsonResponse({'success': False, 'message': 'Missing order_id or customer_email'}, status=400)

        send_order_confirmation_emails(order_id, customer_email)
        return JsonResponse({'success': True, 'message': 'Confirmation emails queued for sending'})
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in send_order_emails request")
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.exception("Error in send_order_emails")
        return JsonResponse({'success': False, 'message': 'Internal server error'}, status=500)

def send_order_confirmation_emails(order_id, customer_email):
    """Send order confirmation emails to customer and manager."""
    try:
        order = Order.objects.get(id=order_id)
        
        customer_subject = "Order Successfully Placed!"
        customer_message = f"""
Dear Customer,

Your order has been successfully placed!

Order Details:
- Order ID: {order.id}
- Item: {order.item}
- Quantity: {order.qty}
- Total Price: {order.total_price} CHF

Thank you for your order. We will start preparing it soon.

Best regards,
Sushi Restaurant
        """
        
        manager_subject = "New Order Received!"
        manager_message = f"""
Hello Manager,

A new order has been received.

Order Details:
- Order ID: {order.id}
- Customer Email: {customer_email}
- Mobile: {order.mobile}
- Item: {order.item}
- Quantity: {order.qty}
- Total Price: {order.total_price} CHF
- Status: {order.status}

Please process this order accordingly.

Best regards,
Order System
        """
        
        from_email = settings.DEFAULT_FROM_EMAIL
        
        send_mail(
            customer_subject,
            customer_message,
            from_email,
            [customer_email],
            fail_silently=False
        )
        
        send_mail(
            manager_subject,
            manager_message,
            from_email,
            [settings.MANAGER_EMAIL],
            fail_silently=False
        )
        
        return True
    except Exception as e:
        logger.exception("Failed to send order confirmation emails for order %s", order_id)
        return False

def privacy_view(request):
    return render(request, 'privacy.html')

def terms_view(request):
    return render(request, 'terms.html')

def cookies_view(request):
    return render(request, 'cookies1.html')
