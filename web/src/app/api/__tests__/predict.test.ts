import { GET } from '../predict/route'

describe('/api/predict', () => {
  describe('GET /api/predict', () => {
    it('should return API documentation', async () => {
      const response = await GET()
      const data = await response.json()

      expect(response.status).toBe(200)
      expect(data.message).toContain('Property Price Prediction API')
      expect(data.required_fields).toContain('listing_price')
      expect(data.required_fields).toContain('living_area')
      expect(data.allowed_models).toContain('lgbm')
    })
  })
})
