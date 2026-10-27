"""Real Linux codecs and existing native normalization preserve the photo contract."""
import io
import pytest
Image=pytest.importorskip('PIL.Image',reason='Linux codec is container-only; native ImageIO covered separately')
from cc_api.profile_photos import normalize,dimensions,PNG

@pytest.mark.parametrize('fmt,mime',[('PNG','image/png'),('JPEG','image/jpeg'),('WEBP','image/webp')])
def test_actual_decoder_normalizes_three_still_formats_and_strips_metadata(fmt,mime):
    image=Image.new('RGB',(700,350),(10,80,120));stream=io.BytesIO()
    options={}
    if fmt=='JPEG':
        exif=Image.Exif();exif[270]='PRIVATE_SYNTHETIC_METADATA';options['exif']=exif
    image.save(stream,format=fmt,**options)
    output=normalize(stream.getvalue(),mime)
    actual,width,height=dimensions(output)
    assert output.startswith(PNG) and actual=='image/png' and max(width,height)<=512
    assert b'PRIVATE_SYNTHETIC_METADATA' not in output
    with Image.open(io.BytesIO(output)) as normalized:
        normalized.load();assert not normalized.getexif()


def test_actual_decoder_rejects_truncated_raster():
    stream=io.BytesIO();Image.new('RGB',(30,30),'blue').save(stream,format='PNG')
    with pytest.raises(ValueError):normalize(stream.getvalue()[:40],'image/png')
