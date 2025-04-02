import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import Stripe from "npm:stripe";
import { createClient } from 'jsr:@supabase/supabase-js@2';
const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY') || '', {
  apiVersion: '2023-10-16'
});
Deno.serve(async (req)=>{
  console.log('hello.');
  // Handle CORS
  if (req.method === 'OPTIONS') {
    console.log('in options if');
    return new Response('ok', {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization'
      }
    });
  }
  try {
    console.log('Webhook received');
    const signature = req.headers.get('stripe-signature');
    if (!signature) {
      console.error('No stripe-signature header found');
      return new Response(JSON.stringify({
        code: 400,
        message: 'Missing stripe-signature header'
      }), {
        status: 400,
        headers: {
          'Content-Type': 'application/json'
        }
      });
    }
    // Get the raw body
    const body = await req.text();
    console.log('Request body:', body.substring(0, 100) + '...');
    console.log('Signature:', signature);
    // Verify webhook signature
    let event;
    try {
      event = await stripe.webhooks.constructEventAsync(
        body,
        signature,
        Deno.env.get('STRIPE_WEBHOOK_SECRET') || ''
      );
    } catch (err) {
      console.error('⚠️ Webhook signature verification failed.', err.message);
      return new Response(JSON.stringify({
        code: 400,
        message: `Webhook signature verification failed: ${err.message}`
      }), {
        status: 400,
        headers: {
          'Content-Type': 'application/json'
        }
      });
    }
    const supabaseClient = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
      {
        auth: {
          autoRefreshToken: false,
          persistSession: false
        }
      }
    );
    // Handle the event
    switch(event.type){
      case 'checkout.session.completed':
        {
          const session = event.data.object;
          console.log('Processing checkout.session.completed:', session.id);
          try {
            // Fetch subscription details from Stripe
            const subscription = await stripe.subscriptions.retrieve(session.subscription);
            console.log('Retrieved subscription:', subscription.id);

            // Update subscription status
            const { data, error } = await supabaseClient.from('subscriptions').upsert({
              user_id: session.client_reference_id,
              stripe_customer_id: session.customer,
              stripe_subscription_id: session.subscription,
              status: subscription.status,
              current_period_end: new Date(subscription.current_period_end * 1000),
              updated_at: new Date()
            }).select('*');
            if (error) throw error;
            console.log('Successfully upserted subscription:', data);
            return new Response(JSON.stringify({
              received: true,
              event: 'checkout.session.completed',
              subscription: data
            }), {
              headers: { 'Content-Type': 'application/json' }
            });
          } catch (err) {
            console.error('Error in checkout.session.completed:', err);
            return new Response(JSON.stringify({
              error: 'Failed to process checkout session',
              details: err.message
            }), {
              status: 500,
              headers: { 'Content-Type': 'application/json' }
            });
          }
        }
      case 'customer.subscription.updated':
        {
          const subscription = event.data.object;
          console.log('Processing customer.subscription.updated:', subscription.id);
          try {
            const { data, error } = await supabaseClient.from('subscriptions').update({
              status: subscription.status,
              current_period_end: new Date(subscription.current_period_end * 1000),
              updated_at: new Date()
            }).eq('stripe_subscription_id', subscription.id);
            if (error) throw error;
            console.log('Successfully updated subscription:', data);
            return new Response(JSON.stringify({
              received: true,
              event: 'customer.subscription.updated',
              subscription: data
            }), {
              headers: { 'Content-Type': 'application/json' }
            });
          } catch (err) {
            console.error('Error in customer.subscription.updated:', err);
            return new Response(JSON.stringify({
              error: 'Failed to update subscription',
              details: err.message
            }), {
              status: 500,
              headers: { 'Content-Type': 'application/json' }
            });
          }
        }
      case 'customer.subscription.deleted':
        {
          const subscription = event.data.object;
          console.log('Processing customer.subscription.deleted:', subscription.id);
          try {
            const { data, error } = await supabaseClient.from('subscriptions').update({
              status: 'canceled',
              updated_at: new Date()
            }).eq('stripe_subscription_id', subscription.id);
            if (error) throw error;
            console.log('Successfully canceled subscription:', data);
            return new Response(JSON.stringify({
              received: true,
              event: 'customer.subscription.deleted',
              subscription: data
            }), {
              headers: { 'Content-Type': 'application/json' }
            });
          } catch (err) {
            console.error('Error in customer.subscription.deleted:', err);
            return new Response(JSON.stringify({
              error: 'Failed to cancel subscription',
              details: err.message
            }), {
              status: 500,
              headers: { 'Content-Type': 'application/json' }
            });
          }
        }
      default:
        return new Response(JSON.stringify({
          received: true,
          event: event.type,
          message: 'Unhandled event type'
        }), {
          headers: { 'Content-Type': 'application/json' }
        });
    }
  } catch (err) {
    console.error('❌ Error processing webhook:', err);
    return new Response(JSON.stringify({
      error: 'Internal server error'
    }), {
      status: 500,
      headers: {
        'Content-Type': 'application/json'
      }
    });
  }
});
