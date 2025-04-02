import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import Stripe from "npm:stripe"
import { createClient } from 'jsr:@supabase/supabase-js@2'

const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY') || '', {
  apiVersion: '2023-10-16'
});

Deno.serve(async (req) => {

  console.log('hello.')

  // Handle CORS
  if (req.method === 'OPTIONS') {
    console.log('in options if')
    return new Response('ok', {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      }
    });
  }

  try {
    
    console.log('in try')
    const supabaseClient = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_ANON_KEY') ?? '',
    )
    // Get the session or user object
    const authHeader = req.headers.get('Authorization')!
    const token = authHeader.replace('Bearer ', '')
    const { data } = await supabaseClient.auth.getUser(token)
    const user = data.user

    console.log('user', user)

    // Get the origin for redirect URLs
    const origin = req.headers.get('Origin') || 'http://localhost:8080'
    console.log('Origin:', origin)

    console.log("sending request to stripe")

    // Create checkout session
    const session = await stripe.checkout.sessions.create({
      payment_method_types: ['card'],
      line_items: [
        {
          price: 'price_1R9TUJFdoeEgAXyvXZdWGewF',
          quantity: 1,
        },
      ],
      mode: 'subscription',
      success_url: `${origin}/thank-you`,
      cancel_url: `${origin}/paywall`,
      client_reference_id: user.id, // This will be used in the webhook
    });

    return new Response(JSON.stringify({ url: session.url }), {
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
    });
  } catch (error) {
    console.error('Error details:', error);
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
    });
  }
}); 