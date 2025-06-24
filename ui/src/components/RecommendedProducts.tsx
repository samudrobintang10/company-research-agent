import React from 'react';

type Product = {
  id: number;
  name: string;
  description?: string;
  note?: string;
  priority?: boolean;
  link?: string;
};

type RecommendedProductsProps = {
  products: Product[];
};

const RecommendedProducts: React.FC<RecommendedProductsProps> = ({ products }) => {
  if (!products || products.length === 0) return null;

  return (
    <div className="bg-white rounded-2xl p-6 shadow-md border border-gray-200 font-['DM_Sans']">
      <h2 className="mb-4 text-xl font-bold">Rekomendasi Produk Bank BJB</h2>
      <ul className="space-y-4">
        {products.map((product) => (
          <li key={product.id} className="pb-3 border-b">
            <h3 className="text-lg font-semibold">{product.name}</h3>
            {product.description && <p className="mt-1 text-sm text-gray-700">{product.description}</p>}
            {product.note && <p className="text-xs italic text-gray-500">{product.note}</p>}
            {product.link && (
              <a
                href={product.link}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block mt-1 text-sm text-blue-600"
              >
                Lihat produk →
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default RecommendedProducts;
