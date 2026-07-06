import { NextRequest } from 'next/server'
import { GET, POST } from '../predict/route'

function makeRequest(body: unknown): NextRequest {
  return new NextRequest('http://localhost/api/predict', {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  })
}

function mockFastApiPrediction(predictedPrice: number, modelId = 'no_list_price') {
  jest.spyOn(global, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        predicted_price: predictedPrice,
        model_used: `price_prediction_model_${modelId}.joblib`,
        model_id: modelId,
        model_type: 'price_tiered_ensemble',
        requires_listing_price: modelId === 'with_list_price',
        status: 'success',
      }),
      {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }
    )
  )
}

afterEach(() => {
  jest.restoreAllMocks()
})

describe('/api/predict', () => {
  describe('GET /api/predict', () => {
    it('should return API documentation', async () => {
      const response = await GET()
      const data = await response.json()

      expect(response.status).toBe(200)
      expect(data.message).toContain('Property Price Prediction API')
      expect(data.required_fields).toContain('living_area')
      expect(data.optional_fields).toContain('listing_price')
      expect(data.allowed_models).toContain('auto')
      expect(data.allowed_models).toContain('no_list_price')
      expect(data.allowed_models).toContain('with_list_price')
    })
  })

  describe('POST /api/predict', () => {
    it('rounds no-list predictions up for the 100k display range', async () => {
      mockFastApiPrediction(2_136_441)

      const response = await POST(makeRequest({ living_area: 55 }))
      const data = await response.json()

      expect(response.status).toBe(200)
      expect(data.predicted_price).toBe(2_136_441)
      expect(data.rounded_predicted_price).toBe(2_200_000)
      expect(data.price_range_min).toBe(2_100_000)
      expect(data.price_range_max).toBe(2_300_000)
      expect(data.price_range_step).toBe(100_000)
    })

    it('keeps listing-aware predictions rounded to the nearest 100k', async () => {
      mockFastApiPrediction(2_136_441, 'with_list_price')

      const response = await POST(makeRequest({ living_area: 55, listing_price: 2_000_000 }))
      const data = await response.json()

      expect(response.status).toBe(200)
      expect(data.rounded_predicted_price).toBe(2_100_000)
      expect(data.price_range_min).toBe(2_000_000)
      expect(data.price_range_max).toBe(2_200_000)
    })

    it('clamps the lower range bound at zero', async () => {
      mockFastApiPrediction(43_000)

      const response = await POST(makeRequest({ living_area: 12 }))
      const data = await response.json()

      expect(response.status).toBe(200)
      expect(data.rounded_predicted_price).toBe(100_000)
      expect(data.price_range_min).toBe(0)
      expect(data.price_range_max).toBe(200_000)
    })
  })
})
